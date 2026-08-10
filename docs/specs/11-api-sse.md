# SDD 11 — API and SSE

> Part of the [FSI Credit Assistant SDD](00-overview.md)
> **Reads:** [04 Graph state](04-graph-state.md), [05 Nodes](05-graph-nodes-and-routing.md)
> **Feeds:** [12 Frontend](12-frontend.md)
> **Implemented by:** `backend/app/main.py`
> **Model:** Sonnet

---

## 1. Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/applications` | Mariana's form → create application + thread, return `application_id` |
| `POST` | `/api/chat` | **SSE.** Body `{thread_id, persona, message}`. Streams trace + tokens. |
| `GET` | `/api/applications?status=manual_review` | Carlos's queue |
| `GET` | `/api/applications/{id}` | Case detail + latest assessment |
| `POST` | `/api/approve` | Resume the `interrupt()` with `Command(resume={...})` |
| `GET` | `/api/trace/{thread_id}` | Historical trace from `decisions_log` |
| `GET` | `/api/health` | Atlas ping + index status |

`/api/health` should report index readiness, not just connectivity. On Friday morning, one
request tells you whether the demo will work.

---

## 2. SSE event contract

Four event types. The frontend must handle all four.

```
event: trace
data: {"node":"policy_retrieval","status":"started","ts":1755180000.12}

event: trace
data: {"node":"policy_retrieval","status":"finished","ms":812,
       "detail":{"op":"$vectorSearch","collection":"credit_policies","k":4,
                 "hits":[{"id":"POL-014","score":0.83,"title":"Limite de LTV..."}]}}

event: token
data: {"text":"Com entrada de 30%"}

event: state
data: {"stage":"negotiation","calc":{...},"decision":{...},"pending_approval":null}

event: done
data: {"thread_id":"APP-20260814-0001"}
```

The `state` event is emitted **once, immediately before `done`**, carrying the final
`stage` / `calc` / `decision` / `pending_approval`. Emitting it per node would make the UI
flicker through intermediate states that were never real conclusions.

---

## 3. How the events are produced

```python
async for mode, chunk in graph.astream(
    payload,
    config={"configurable": {"thread_id": thread_id}},
    stream_mode=["updates", "messages", "custom"],
):
    ...
```

| `stream_mode` | Produces | Becomes |
|---|---|---|
| `updates` | Node boundaries | `trace` events with `status: started/finished` |
| `messages` | LLM tokens | `token` events |
| `custom` | Whatever nodes emit via `get_stream_writer()` | The `detail` payload inside `trace` |

Rich detail is emitted from inside nodes:

```python
from langgraph.config import get_stream_writer

def policy_retrieval(state: AgentState) -> dict:
    writer = get_stream_writer()
    writer({"op": "$vectorSearch", "collection": "credit_policies", "k": 4})
    docs = vector_store.similarity_search(query, k=4, pre_filter={"product": product})
    writer({"hits": [{"id": d.metadata["_id"], "score": d.metadata.get("score")} for d in docs]})
    return {"policies": [d.metadata | {"text": d.page_content} for d in docs]}
```

### Why `astream` and not `stream_events(version="v3")`

The trace panel needs **node boundaries**, which `stream_mode="updates"` gives directly.
`stream_events` is available and `version="v3"` is real (verified —
[13 §5](13-verified-api-contract.md)), but it adds a projection layer this design does not
need.

> **If any code does use `stream_events`, it must pass `version="v3"` explicitly.** The
> default is still `"v2"`, and pre-2026 training data will produce the v2 event shape. This
> is a known, specific hallucination risk for the executing model.

---

## 4. The trace panel must be true

Every trace event originates from actual graph execution. **No simulated timings, no
hardcoded step lists, no `setTimeout` animations.** If a node is skipped, the panel shows it
skipped.

The panel's entire value in the interview is that it is *evidence*. An interviewer who
catches one fabricated step discounts everything else on screen — including the parts that
were real.

---

## Acceptance criteria

- [ ] `curl -N -X POST localhost:8000/api/chat -d '{...}'` streams all four event types.
      This command goes in `docs/demo-script.md` as the frontend fallback.
- [ ] Node timings in `trace` events are measured, never estimated.
- [ ] `policy_retrieval` and `precedent_search` emit real matched IDs and scores.
- [ ] `state` fires exactly once per request, immediately before `done`.
- [ ] `/api/approve` resumes an interrupted thread and the graph reaches `persist_decision`.
- [ ] `/api/health` reports index readiness, not only connectivity.
- [ ] No `stream_events` call anywhere lacks an explicit `version="v3"`.
