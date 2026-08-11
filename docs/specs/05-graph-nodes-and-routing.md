# SDD 05 — Graph nodes and routing

> Part of the [FSI Credit Assistant SDD](00-overview.md) · Satisfies **R1**
> **Reads:** [04 Graph state](04-graph-state.md), [02 Data model](02-data-model.md)
> **Feeds:** [06 Negotiation](06-negotiation-agent.md), [11 API](11-api-sse.md)
> **Implemented by:** `backend/app/graph/nodes/*.py`, `backend/app/graph/builder.py`
> **Model:** Sonnet (`builder.py` is **[OPUS]**)

---

## 1. Nodes

The negotiation node has its own file — [06](06-negotiation-agent.md). Everything else is
here.

| Node | Type | Responsibility |
|---|---|---|
| `router` | deterministic | Dispatch on `persona` + `stage`. Pure function, no I/O. |
| `intake` | LLM (structured output) | Extract/normalise loan parameters from free text into `CreditApplication`. If required fields are missing, leave them `None` and route back to ask. |
| `load_context` | deterministic | Read `customer_profiles` + `MongoDBStore` memories into state. |
| `policy_retrieval` | vector search | `$vectorSearch` on `credit_policies`, `pre_filter` by product. k=4. |
| `credit_calculator` | **pure Python** | PMT, CET, LTV, DTI. No LLM. See [10](10-domain-credit.md). |
| `decision` | deterministic rules | Apply `domain/rules.py`. Writes an `assessment` event to `decisions_log` and updates `applications.status` + `latest_assessment`. |
| `customer_response` | LLM | Write Mariana's answer in plain Portuguese, grounded in `policies` + `calc`. Also handles the "missing fields" branch. |
| `precedent_search` | vector search | `$vectorSearch` on `historical_cases`, `pre_filter` by product. k=3. |
| `analyst_brief` | LLM | Produce the case dossier: recommendation + explainability + precedent citations. |
| `negotiation` | **Deep Agent** | Wrapper node around `create_deep_agent` with 2 subagents. See [06](06-negotiation-agent.md). **[OPUS]** |
| `await_approval` | `interrupt()` | Pause and persist before any write to `decisions_log`. |
| `persist_decision` | deterministic | Write log entry, new precedent (with embedding), memory updates. |

### Node implementation rules

- **Every node returns a partial state dict.** Never mutate the input state in place.
- **Every retrieval and memory node emits trace detail** via `get_stream_writer()` — see
  [11 §2](11-api-sse.md). The trace panel is only valuable if it is true.
- **LLM nodes never compute numbers.** They receive `calc` in state and describe it.
- **`decision` and `persist_decision` are the only nodes that write `applications`**, and
  `persist_decision` is the only node that writes `historical_cases`.

> An earlier draft of this file gave `applications` a single writer. That is unimplementable:
> [02 §5](02-data-model.md) lists `approved` and `approved_with_conditions` among the valid
> `status` values, and only the analyst path can produce them. With one writer, Carlos's queue
> would never clear. `decision` owns the automatic outcomes, `persist_decision` owns the
> post-approval ones, and nothing else touches the collection.

### `persist_decision` writes three things

1. A `final_decision` (or `human_approval`) event to `decisions_log`.
2. A new document in `historical_cases`, **with a freshly generated embedding**, making the
   just-decided case immediately retrievable. See [08 §4](08-retrieval.md).
3. Memory updates to `MongoDBStore` across the three namespaces in
   [07 §2](07-memory.md).

---

## 2. Edges

```python
builder.add_edge(START, "router")
builder.add_conditional_edges("router", route, {
    "intake": "intake",
    "precedent_search": "precedent_search",
    "negotiation": "negotiation",
})

# customer path
builder.add_conditional_edges("intake", has_complete_application, {
    "complete": "load_context",
    "incomplete": "customer_response",      # ask for the missing fields
})
builder.add_edge("load_context", "policy_retrieval")
builder.add_edge("policy_retrieval", "credit_calculator")
builder.add_edge("credit_calculator", "decision")
builder.add_edge("decision", "customer_response")
builder.add_edge("customer_response", END)

# analyst path
builder.add_edge("precedent_search", "analyst_brief")
builder.add_edge("analyst_brief", END)

builder.add_conditional_edges("negotiation", needs_approval, {
    "await_approval": "await_approval",
    "end": END,
})
builder.add_edge("await_approval", "persist_decision")
builder.add_edge("persist_decision", END)
```

---

## 3. Routing functions

```python
def route(state: AgentState) -> str:
    if state["persona"] == "analyst":
        return "precedent_search" if state["stage"] == "review" else "negotiation"
    return "intake"


def has_complete_application(state: AgentState) -> str:
    app = state.get("application")
    required = ("product", "asset_value", "down_payment", "term_months")
    return "complete" if app and all(app.get(f) is not None for f in required) else "incomplete"


def needs_approval(state: AgentState) -> str:
    return "await_approval" if state.get("pending_approval") else "end"
```

### Why `intake` has a conditional edge

`intake` is the boundary between free-form natural language and typed code. If Mariana
writes *"quero financiar um apartamento"* with no amount and no term, an unconditional edge
would carry `None` into the calculator and produce a division error — or worse, a plausible
number computed from a default.

**General rule: every extraction node needs a conditional edge behind it.** Extraction is
where the type system stops protecting you.

### Why customer turns always route to `intake`

`route()` sends a customer turn to `intake` regardless of stage. This is intentional: a
re-simulation (*"e se eu desse mais entrada?"*) is just a new intake on the same thread.
`intake` sees the prior `application` in state, so it patches the changed fields rather than
re-asking for everything.

---

## Acceptance criteria

- [ ] All 12 nodes exist and return partial state dicts.
- [ ] `tests/test_graph_smoke.py` covers: complete intake → assessment; incomplete intake →
      `customer_response` without touching the calculator; analyst entry at `stage="review"`
      → `precedent_search`.
- [ ] Sending a customer message with no amount produces a clarifying question and **no**
      `decisions_log` entry.
- [ ] An auto-approved application produces exactly one `assessment` event in
      `decisions_log`.
- [ ] `policy_retrieval` and `precedent_search` each emit a `custom` stream event containing
      the matched IDs and scores.
