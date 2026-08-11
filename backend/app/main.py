"""SDD 11 — FastAPI + SSE.

`/api/chat` and `/api/approve` need the compiled graph, built once per
process in `lifespan` (SDD 04 §4) from `graph.builder.build_graph` — deferred
to the Opus session (SDD 04/05). Importing it only happens inside `lifespan`,
so the app module itself, and the five endpoints that don't touch the graph,
work today.
"""

import json
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk, HumanMessage
from langgraph.types import Command
from pydantic import BaseModel

from app.db import get_db
from app.memory.checkpointer import get_checkpointer
from app.memory.store import get_store


class CreateApplicationRequest(BaseModel):
    customer_id: str
    product: Literal["mortgage", "auto"]
    asset_value: float
    down_payment: float
    term_months: int
    purpose: str = ""


class ChatRequest(BaseModel):
    thread_id: str
    persona: Literal["customer", "analyst"]
    message: str


class ApproveRequest(BaseModel):
    thread_id: str
    resume: dict


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.graph.builder import build_graph  # SDD 04/05 — [OPUS], deferred

    app.state.graph = build_graph(checkpointer=get_checkpointer(), store=get_store())
    yield


app = FastAPI(title="FSI Credit Assistant", lifespan=lifespan)


def _new_application_id() -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    db = get_db()
    seq = db["applications"].count_documents({"_id": {"$regex": f"^APP-{today}"}}) + 1
    return f"APP-{today}-{seq:04d}"


@app.post("/api/applications")
def create_application(body: CreateApplicationRequest):
    application_id = _new_application_id()
    now = datetime.now(timezone.utc)
    doc = {
        "_id": application_id,
        "thread_id": application_id,
        "customer_id": body.customer_id,
        "product": body.product,
        "asset_value": body.asset_value,
        "down_payment": body.down_payment,
        "requested_amount": body.asset_value - body.down_payment,
        "term_months": body.term_months,
        "purpose": body.purpose,
        "status": "draft",
        "created_at": now,
        "updated_at": now,
        "latest_assessment": None,
    }
    get_db()["applications"].insert_one(doc)
    return {"application_id": application_id}


@app.get("/api/applications")
def list_applications(status: str | None = None):
    query = {"status": status} if status else {}
    docs = list(get_db()["applications"].find(query).sort("created_at", -1))
    return {"applications": docs}


@app.get("/api/applications/{application_id}")
def get_application(application_id: str):
    doc = get_db()["applications"].find_one({"_id": application_id})
    if doc is None:
        raise HTTPException(status_code=404, detail="application not found")
    return doc


@app.get("/api/trace/{thread_id}")
def get_trace(thread_id: str):
    # `decisions_log` entries are inserted without an `_id`, so Mongo assigns an
    # ObjectId, which FastAPI's encoder cannot serialise. Project it away: the
    # trace panel identifies events by `application_id` + `seq`.
    docs = list(
        get_db()["decisions_log"].find({"thread_id": thread_id}, {"_id": 0}).sort("seq", 1)
    )
    return {"thread_id": thread_id, "events": docs}


def _index_status(db, collection_name: str) -> dict:
    try:
        for idx in db[collection_name].list_search_indexes():
            if idx.get("name") == "vector_index":
                return {"exists": True, "queryable": bool(idx.get("queryable", True))}
        return {"exists": False, "queryable": False}
    except Exception as exc:  # index API unavailable, e.g. no Atlas Search on this cluster
        return {"exists": False, "queryable": False, "error": str(exc)}


@app.get("/api/health")
def health():
    db = get_db()
    try:
        db.client.admin.command("ping")
        connected = True
    except Exception:
        connected = False

    indexes = {
        name: _index_status(db, name)
        for name in ("credit_policies", "historical_cases", "agent_memories")
    }
    return {"connected": connected, "indexes": indexes}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str, ensure_ascii=False)}\n\n"


# Nodes whose LLM calls are machinery rather than prose. `intake` uses
# `with_structured_output`, so streaming it verbatim puts raw extraction JSON in
# the customer's chat window. Everything else is presentational by default, so
# `analyst_brief` and `negotiation` stream as soon as session 6 adds them.
_SILENT_LLM_NODES = {"intake"}


def _is_customer_facing_token(message_chunk, meta: dict) -> bool:
    """SDD 11 §2 — a `token` event is a piece of the answer being written.

    `stream_mode="messages"` yields two different things under one mode: the
    `AIMessageChunk`s an LLM emits while streaming, and the finished `AIMessage`
    a node writes into `messages`. Forwarding both sends the whole answer twice,
    once token by token and once entire.
    """
    if not isinstance(message_chunk, AIMessageChunk):
        return False
    return meta.get("langgraph_node") not in _SILENT_LLM_NODES


def _hydrate_application(thread_id: str, existing: dict | None) -> dict | None:
    """SDD 04 §1 — `thread_id == application_id`.

    The graph has no other way to learn which application it is working on:
    `/api/chat` carries a thread id, and `decision` needs an `application_id`
    while `load_context` needs a `customer_id`. This is where HTTP identity
    becomes graph state.

    Anything already in the checkpoint wins over the stored row, because
    `application` is an overwrite field: re-hydrating it wholesale on every
    turn would discard the patches `intake` made on previous turns and silently
    undo a re-simulation.
    """
    row = get_db()["applications"].find_one({"_id": thread_id})
    if row is None:
        return existing

    stored = {
        "application_id": row["_id"],
        "customer_id": row.get("customer_id"),
        "product": row.get("product"),
        "asset_value": row.get("asset_value"),
        "down_payment": row.get("down_payment"),
        "requested_amount": row.get("requested_amount"),
        "term_months": row.get("term_months"),
        "purpose": row.get("purpose", ""),
    }
    return {**stored, **(existing or {})}


async def stream_chat_events(
    graph, thread_id: str, persona: str, message: str
) -> AsyncIterator[str]:
    """SDD 11 §2-3 — maps `astream(..., stream_mode=["updates","messages","custom"])`
    onto the four SSE event types.

    `updates` only fires once a node *finishes* (verified by introspection —
    it carries no separate start signal). `started`/`finished` are therefore
    both emitted at that point, with `ms` measured as real wall-clock elapsed
    since the previous node boundary — a true measurement of that node's
    execution, not an estimate, because this graph's customer path has no
    parallel branches.
    """
    config = {"configurable": {"thread_id": thread_id}}
    payload = {"persona": persona, "messages": [HumanMessage(message)]}

    snapshot = await graph.aget_state(config)
    application = _hydrate_application(thread_id, snapshot.values.get("application"))
    if application is not None:
        payload["application"] = application

    t_prev = time.perf_counter()
    pending_detail: dict = {}
    final_state: dict = {}

    async for mode, chunk in graph.astream(
        payload, config=config, stream_mode=["updates", "messages", "custom"]
    ):
        if mode == "custom":
            # The negotiation node runs a nested graph, whose tokens and stream
            # writes do not reach this `astream` on their own. It forwards both
            # through the parent's writer, so they arrive here as `custom`:
            #
            #   `token` — a piece of the agent's answer, relayed as it is written;
            #   `step`  — a tool or subagent announcing itself mid-node.
            #
            # Both are flushed immediately. Buffering them to the node boundary
            # like an ordinary `detail` would leave the screen blank for the
            # whole negotiation and then print everything at once, which is the
            # failure mode SDD 06 §6 exists to prevent.
            if "token" in chunk:
                yield _sse("token", {"text": chunk["token"]})
            elif "step" in chunk:
                yield _sse("trace", {"status": "step", "ts": time.time(), **chunk})
            else:
                pending_detail.update(chunk)
        elif mode == "updates":
            for node, update in chunk.items():
                now = time.perf_counter()
                ms = int((now - t_prev) * 1000)
                t_prev = now

                # `await_approval` calling `interrupt()` arrives under the
                # reserved `__interrupt__` key, and its payload is a tuple of
                # `Interrupt` objects rather than a state update. It is a
                # third status, not a finished node: the graph is paused and
                # waiting for `POST /api/approve`, which is exactly what the
                # trace panel should show (SDD 06 §5).
                if node == "__interrupt__":
                    yield _sse(
                        "trace",
                        {"node": "await_approval", "status": "interrupted", "ts": time.time()},
                    )
                    continue

                yield _sse("trace", {"node": node, "status": "started", "ts": time.time() - ms / 1000})
                event = {"node": node, "status": "finished", "ms": ms}
                if pending_detail:
                    event["detail"] = pending_detail
                    pending_detail = {}
                yield _sse("trace", event)

                if update:
                    final_state.update(update)
        elif mode == "messages":
            message_chunk, meta = chunk
            if not _is_customer_facing_token(message_chunk, meta):
                continue
            text = getattr(message_chunk, "content", "")
            if text:
                yield _sse("token", {"text": text})

    yield _sse(
        "state",
        {
            "stage": final_state.get("stage"),
            "calc": final_state.get("calc"),
            "decision": final_state.get("decision"),
            "pending_approval": final_state.get("pending_approval"),
        },
    )
    yield _sse("done", {"thread_id": thread_id})


@app.post("/api/chat")
async def chat(body: ChatRequest, request: Request):
    graph = request.app.state.graph
    return StreamingResponse(
        stream_chat_events(graph, body.thread_id, body.persona, body.message),
        media_type="text/event-stream",
    )


@app.post("/api/approve")
async def approve(body: ApproveRequest, request: Request):
    graph = request.app.state.graph
    config = {"configurable": {"thread_id": body.thread_id}}
    result = await graph.ainvoke(Command(resume=body.resume), config=config)
    return {"stage": result.get("stage"), "decision": result.get("decision")}
