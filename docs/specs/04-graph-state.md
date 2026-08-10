# SDD 04 — Graph state

> Part of the [FSI Credit Assistant SDD](00-overview.md) · Satisfies part of **R1**
> **Reads:** [02 Data model](02-data-model.md) · **Feeds:** [05 Nodes](05-graph-nodes-and-routing.md), [06 Negotiation](06-negotiation-agent.md), [07 Memory](07-memory.md)
> **Implemented by:** `backend/app/graph/state.py`, `backend/app/graph/builder.py`
> **Model:** Sonnet (`builder.py` is **[OPUS]**)

---

## 1. One thread, two personas

`thread_id == application_id`.

Mariana's simulation creates the thread. When the decision is `manual_review`, the
application lands in Carlos's queue carrying that same `thread_id`. Carlos resumes the
**same** thread.

Consequence: the full context of Mariana's conversation is available to Carlos's agent with
no explicit handoff payload, because it lives in `checkpoints` on Atlas rather than in a
process's memory.

This is a demo beat, not an implementation detail — beat 5 in [16](16-demo-plan.md). Say the
words "same thread ID" while pointing at the screen.

---

## 2. State schema

`backend/app/graph/state.py`:

```python
from typing import Annotated, Literal, TypedDict
import operator
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class CreditApplication(TypedDict):
    application_id: str
    customer_id: str
    product: Literal["mortgage", "auto"]
    asset_value: float
    down_payment: float
    requested_amount: float
    term_months: int
    purpose: str


class CalcResult(TypedDict):
    monthly_payment: float
    total_interest: float
    annual_rate: float
    cet_annual: float
    ltv: float
    dti: float
    schedule_preview: list[dict]


class Decision(TypedDict):
    outcome: Literal["auto_approved", "manual_review", "denied"]
    reasons: list[str]
    policy_refs: list[str]
    breached_rules: list[str]


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    persona: Literal["customer", "analyst"]
    stage: Literal["intake", "assessment", "review", "negotiation", "closed"]
    application: CreditApplication | None
    profile: dict | None
    memories: list[dict]
    policies: list[dict]
    precedents: list[dict]
    calc: CalcResult | None
    decision: Decision | None
    scenarios: Annotated[list[dict], operator.add]
    pending_approval: dict | None
```

### Why `scenarios` uses `operator.add`

Every negotiation scenario accumulates instead of overwriting. The scenario history is
itself demo material — the `ScenarioTable` component renders it, and "we tried five
structures in ninety seconds" is the business value made visible.

Every other field uses default overwrite semantics. Only `messages` (via `add_messages`) and
`scenarios` are reducers. Getting this wrong is a common LangGraph mistake: a reducer on a
field that should be replaced produces state that silently grows and confuses the model.

---

## 3. Stage transitions

Exhaustive. Every node that mutates `stage` is listed. If a node is not here, it must not
write `stage`.

| Node | Sets `stage` to | When |
|---|---|---|
| `intake` | `assessment` | application is complete |
| `intake` | unchanged | required fields missing |
| `decision` | `review` | outcome is `manual_review` |
| `decision` | `closed` | outcome is `auto_approved` or `denied` |
| `analyst_brief` | `negotiation` | always |
| `persist_decision` | `closed` | always |

In a graph where two personas share one thread, "who mutates `stage` and when" is the
primary source of routing bugs. This table is the contract.

---

## 4. Compilation

```python
graph = builder.compile(checkpointer=checkpointer, store=store)
```

Both are `compile()` parameters — verified signature in
[13 §5](13-verified-api-contract.md). The store is then reachable from inside any node via
`langgraph.config.get_store()`, so nodes do not need it injected.

Build the graph **once per process**, at application startup. Never per request, never per
session. This is what makes the kill-and-resume beat work ([07 §3](07-memory.md)) and what
keeps the degradation guarantee in [01 §4](01-architecture.md) true.

---

## Acceptance criteria

- [ ] `state.py` type-checks; `AgentState` has exactly two reducer fields (`messages`,
      `scenarios`).
- [ ] The graph compiles with both `checkpointer` and `store` supplied.
- [ ] Two consecutive `invoke` calls on the same `thread_id` show accumulated `messages` and
      `scenarios`, and overwritten `calc`.
- [ ] No node writes `stage` outside the table in §3.
- [ ] `tests/test_graph_smoke.py` drives the customer path end-to-end with a fake LLM and
      asserts the stage sequence `intake → assessment → review`.
