"""SDD 11 — FastAPI + SSE.

`/api/chat` and `/api/approve` need the compiled graph, built once per
process in `lifespan` (SDD 04 §4) from `graph.builder.build_graph` — deferred
to the Opus session (SDD 04/05). Importing it only happens inside `lifespan`,
so the app module itself, and the five endpoints that don't touch the graph,
work today.
"""

import asyncio
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
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

# The frontend (SDD 12) is a separate Next.js origin — localhost:3000 talking
# to localhost:8000 is cross-origin by the browser's same-origin rule (port
# differs), so `/api/chat`'s `fetch()` is silently rejected without this.
# Demo has no auth and no cookies, so an explicit origin allowlist without
# credentials is enough; it does not need to be locked down further.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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
def list_applications(status: str | None = None, customer_id: str | None = None):
    query: dict = {}
    if status:
        query["status"] = status
    if customer_id:
        query["customer_id"] = customer_id
    docs = list(get_db()["applications"].find(query).sort("created_at", -1))
    return {"applications": docs}


@app.get("/api/applications/{application_id}")
def get_application(application_id: str):
    doc = get_db()["applications"].find_one({"_id": application_id})
    if doc is None:
        raise HTTPException(status_code=404, detail="application not found")
    return doc


def _message_text(message) -> str:
    """Same text-extraction rule as `agent/negotiation.py`'s `_text` — content
    is a plain string for ordinary turns, or a list of content-block dicts for
    some provider responses. Duplicated rather than imported: that helper
    lives in the deep-agent module for a `messages` list shaped by the graph's
    own reducer, not the deep agent.
    """
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    return "".join(part.get("text", "") for part in content if isinstance(part, dict))


@app.get("/api/history/{thread_id}")
async def get_history(thread_id: str, request: Request):
    """The real conversation for a thread, read back from the LangGraph
    checkpoint — the only durable copy of it. `decisions_log` (`/api/trace`)
    is a structured audit trail of *events*, not the prose turns themselves;
    `applications` carries only the latest snapshot. Only human/AI turns are
    returned: `AgentState.messages` never carries a bare SystemMessage or a
    deep-agent tool-call message (`agent/negotiation.py`'s `_map_result` only
    ever appends the agent's final answer), so no filtering beyond message
    type is needed to keep this to what the customer or analyst actually saw.
    """
    graph = request.app.state.graph
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = await graph.aget_state(config)
    raw_messages = snapshot.values.get("messages") or []

    messages = []
    for message in raw_messages:
        if message.type not in ("human", "ai"):
            continue
        text = _message_text(message)
        if not text:
            continue
        messages.append({"role": "user" if message.type == "human" else "assistant", "text": text})

    return {"thread_id": thread_id, "messages": messages}


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


# Item 10 — a durable copy of "Trace ao vivo" in its own collection. Kept as a
# module-level set only so a fire-and-forget `asyncio.create_task` isn't
# garbage-collected mid-write once `stream_chat_events` returns and its local
# variables go out of scope (asyncio's own recommendation for tasks nobody
# awaits — see `asyncio.create_task` docs).
_background_tasks: set[asyncio.Task] = set()


def _write_trace_log(thread_id: str, persona: str, events: list[dict]) -> None:
    if not events:
        return
    get_db()["trace_log"].insert_one(
        {
            "thread_id": thread_id,
            "persona": persona,
            "events": events,
            "recorded_at": datetime.now(timezone.utc),
        }
    )


def _persist_trace_log(thread_id: str, persona: str, events: list[dict]) -> None:
    """Schedules the write for *after* the caller's SSE generator is done —
    called as the last statement in `stream_chat_events`, once every frame
    has already been yielded to the client. `pymongo`'s client is
    synchronous, so the insert itself runs off the event loop via
    `asyncio.to_thread`; wrapping that in `create_task` rather than awaiting
    it means the request handler returns immediately and this write never
    sits on the customer's critical path.
    """
    task = asyncio.create_task(asyncio.to_thread(_write_trace_log, thread_id, persona, events))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


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


def _hydrate_application(row: dict | None, existing: dict | None) -> dict | None:
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
        # Item 10 — unlike the negotiable inputs above, `status` is never
        # written into checkpoint state by any node (`persist_decision`
        # doesn't return it), so it always comes from here: the one place
        # that can tell the negotiation agent a case it's reopening was
        # already approved/denied by a human, not still pending.
        "status": row.get("status"),
    }
    return {**stored, **(existing or {})}


def _hydrate_decision_context(
    row: dict | None, existing_calc: dict | None, existing_decision: dict | None
) -> tuple[dict | None, dict | None]:
    """Sibling of `_hydrate_application` for `calc`/`decision`.

    Every case that reached Carlos's queue *used to* have gotten there by
    running through the live customer-path graph first, which always leaves
    `calc`/`decision` in the checkpoint before an analyst ever opens it. An
    application seeded straight into `applications` (Part B of the demo
    data) skips that entirely — its checkpoint has neither — so
    `analyst_brief`'s dossier and `negotiation`'s case briefing would open on
    a blank assessment. Same "checkpoint wins" rule as `_hydrate_application`:
    only fall back to the stored row when the checkpoint truly has nothing,
    never overwrite a live negotiation's own recalculated state.
    """
    if row is None or existing_calc is not None or existing_decision is not None:
        return existing_calc, existing_decision
    latest_assessment = row.get("latest_assessment") or {}
    calc = latest_assessment.get("calc")
    decision = row.get("final_decision") or latest_assessment.get("decision")
    return calc, decision


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
    row = get_db()["applications"].find_one({"_id": thread_id})
    application = _hydrate_application(row, snapshot.values.get("application"))
    if application is not None:
        payload["application"] = application
    calc, decision = _hydrate_decision_context(row, snapshot.values.get("calc"), snapshot.values.get("decision"))
    if calc is not None:
        payload["calc"] = calc
    if decision is not None:
        payload["decision"] = decision

    t_prev = time.perf_counter()
    pending_detail: dict = {}
    trace_events: list[dict] = []

    def emit_trace(data: dict) -> str:
        trace_events.append(data)
        return _sse("trace", data)

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
                yield emit_trace({"status": "step", "ts": time.time(), **chunk})
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
                    yield emit_trace({"node": "await_approval", "status": "interrupted", "ts": time.time()})
                    continue

                yield emit_trace({"node": node, "status": "started", "ts": time.time() - ms / 1000})
                event = {"node": node, "status": "finished", "ms": ms}
                if pending_detail:
                    event["detail"] = pending_detail
                    pending_detail = {}
                yield emit_trace(event)
        elif mode == "messages":
            message_chunk, meta = chunk
            if not _is_customer_facing_token(message_chunk, meta):
                continue
            text = getattr(message_chunk, "content", "")
            if text:
                yield _sse("token", {"text": text})

    # Read the checkpoint rather than replaying the `updates` deltas: `scenarios`
    # is an `operator.add` field (SDD 04 §2), so a node's own delta is only
    # what *that turn* contributed, never the accumulated thread total.
    # `calc`/`decision`/`pending_approval`/`stage` use plain overwrite
    # semantics, so the checkpoint agrees with the last delta for those either
    # way — one read after the loop is simpler and correct for both kinds.
    final_values = (await graph.aget_state(config)).values
    yield _sse(
        "state",
        {
            "stage": final_values.get("stage"),
            "calc": final_values.get("calc"),
            "decision": final_values.get("decision"),
            "pending_approval": final_values.get("pending_approval"),
            "scenarios": final_values.get("scenarios"),
        },
    )
    yield _sse("done", {"thread_id": thread_id})

    # Item 10 — persist the same trace the panel just showed, after every SSE
    # frame for this turn has already reached the client.
    _persist_trace_log(thread_id, persona, trace_events)


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
