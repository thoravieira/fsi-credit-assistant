# SDD 06 — Negotiation agent **[OPUS]**

> Part of the [FSI Credit Assistant SDD](00-overview.md) · Satisfies **R4**
> **Reads:** [04 Graph state](04-graph-state.md), [10 Credit domain](10-domain-credit.md), [08 Retrieval](08-retrieval.md)
> **Implemented by:** `backend/app/graph/nodes/negotiation.py`, `backend/app/graph/tools/*.py`, `backend/app/graph/prompts/negotiation.md`
> **Model: [OPUS].** This node is the technical and narrative core of the demo.

---

## 1. Why this node exists

Everything else in the graph is a deterministic workflow. This is the one place where the
LLM decides what to do next, and it is what makes the answer to *"is this an agent or a
workflow?"* honest.

The intended answer to that question: **both, deliberately.** The high-volume,
low-ambiguity path is deterministic because it must be cheap and auditable. Expensive
reasoning is reserved for cases that already fell into exception. The criterion is cost and
auditability, not fashion.

That is a Solutions Architect answer. "It's 100% agentic!" invites the next question and
does not survive it.

---

## 2. Tools

`create_react_agent` with exactly four tools:

```python
recalculate_scenario(amount: float, term_months: int,
                     down_payment: float, annual_rate: float | None) -> CalcResult
search_policy(query: str, product: str) -> list[PolicyChunk]
search_precedents(query: str, product: str, decision: str | None) -> list[Case]
check_open_finance_assets(customer_id: str) -> OpenFinanceAssets
```

| Tool | Delegates to | Notes |
|---|---|---|
| `recalculate_scenario` | `domain/calculator.py` | **The LLM never computes a number.** Appends to `state["scenarios"]` and writes a `scenario_simulated` event to `decisions_log`. |
| `search_policy` | `retrieval/policies.py` | Same `$vectorSearch` path as the `policy_retrieval` node |
| `search_precedents` | `retrieval/precedents.py` | Same path as the `precedent_search` node |
| `check_open_finance_assets` | `customer_profiles.open_finance` | Simulates a consent-gated Open Finance share. Returns assets **only** when `consent_granted` is true; otherwise returns a "consent required" result the agent must surface to Carlos. |

`check_open_finance_assets` is the cuttable one (Wednesday's scope valve, per
[16](16-demo-plan.md)). The other three are core.

### The separation that matters

The model chooses *which* scenario to evaluate; deterministic Python evaluates it. This is
the entire answer to *"how do you stop it hallucinating financials?"* — and it is
demonstrable by opening `calculator.py` on stage.

---

## 3. Prompt contract

`backend/app/graph/prompts/negotiation.md`, versioned. The version string is written into
every `decisions_log` entry as `prompt_version`.

The system prompt must:

1. Establish the analyst's role and that **recommendations require human approval**.
2. Require citing policy IDs (`POL-xxx`) for any eligibility claim.
3. **Forbid asserting any figure not returned by `recalculate_scenario`.** No mental
   arithmetic, no interpolation, no "roughly".
4. Instruct that when Carlos signals a final decision (*"aprovar"*, *"negar"*, *"aprovar com
   condições"*), the agent populates `pending_approval` and stops — it does not conclude on
   its own.
5. Keep responses short. Carlos is reading on screen while an audience watches; a
   twelve-paragraph answer kills the demo's pace.

Prompts are versioned files, not string literals in Python. Prompt provenance is part of the
audit trail and answers *"which version of the system made this decision?"* with a field
rather than a shrug.

---

## 4. Approval gate

When `pending_approval` is set, routing sends the graph to `await_approval`, which calls
`interrupt()`. The graph pauses, and its state is persisted to `checkpoints` on Atlas.
Carlos's approval arrives via `POST /api/approve`, which resumes with
`Command(resume={...})`.

```python
from langgraph.types import interrupt, Command

def await_approval(state: AgentState) -> dict:
    decision = interrupt(state["pending_approval"])
    return {"pending_approval": None, "decision": decision}
```

`interrupt` is used at exactly **one** point, not as the conversational mechanism. Ordinary
negotiation turns are plain `invoke` calls on the same `thread_id`; the checkpointer
restores state. This is simpler and far more robust live than an interrupt/resume loop.

### Why this is worth a node

*"Why isn't it fully automatic?"* is the most likely business objection. Because
`await_approval` is a graph node with `interrupt()`, the answer stops being philosophical:
**the agent cannot write a decision without a human resume.** It is architecture, not policy
— and it is visible in the trace panel as a paused step.

---

## 5. Scenario levers for the demo

The negotiation should be able to move all of these, because these are what Carlos actually
does:

- Reduce the financed amount
- Increase the down payment (drops LTV)
- Extend the term (drops instalment, raises total interest — and can breach the age rule)
- Adjust the rate within the analyst's authority (alçada)
- Request Open Finance asset sharing as a mitigant

Rehearse three of them in sequence for beat 6. The third should be the Open Finance one:
it moves the case from "no" to "yes" for a *business* reason rather than a numeric one,
which is the strongest moment in the demo.

---

## Acceptance criteria

- [ ] The agent never states a figure absent from a `recalculate_scenario` result.
      Verify by reading three full transcripts, not by hoping.
- [ ] Every eligibility claim in the output cites at least one `POL-xxx` id.
- [ ] Three consecutive scenarios accumulate in `state["scenarios"]` and render in
      `ScenarioTable`.
- [ ] Each scenario produces a `scenario_simulated` entry in `decisions_log`, including the
      ones Carlos rejects.
- [ ] Saying "aprovar" sets `pending_approval` and reaches `await_approval` — and writes
      **nothing** to `decisions_log` as a final decision until `/api/approve` is called.
- [ ] `prompt_version` appears in every logged entry.
- [ ] Median response time per negotiation turn under 6 s with token streaming enabled.
