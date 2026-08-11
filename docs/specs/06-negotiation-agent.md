# SDD 06 — Negotiation deep agent **[OPUS]**

> Part of the [FSI Credit Assistant SDD](00-overview.md) · Satisfies **R4**
> **Reads:** [04 Graph state](04-graph-state.md), [10 Credit domain](10-domain-credit.md), [08 Retrieval](08-retrieval.md)
> **Implemented by:** `backend/app/agent/negotiation.py`, `backend/app/agent/subagents.py`, `backend/app/graph/tools/*.py`, `backend/app/graph/prompts/*.md`
> **Model: [OPUS].** This is the technical and narrative core of the demo.

---

## 1. The three-layer split

The stack is chosen per problem type, not by picking the newest tool for everything. This is
itself an interview answer.

| Layer | Technology | Where | Why |
|---|---|---|---|
| **Conversation** | LangChain | `intake`, `customer_response`, `analyst_brief` | Chat models, structured output, message handling. Deterministic in shape, LLM in content. |
| **Workflow** | LangGraph | `router` → `decision`, `persist_decision` | High-volume, low-ambiguity path. Must be cheap, predictable and auditable. |
| **Reasoning** | **Deep Agents** | `negotiation` only | The one place where the problem is genuinely open-ended: exploring credit structures under policy constraints. |

**The answer to "is this an agent or a workflow?"**: both, deliberately, and the boundary is
drawn on cost and auditability rather than fashion. Roughly 90% of requests never touch the
reasoning layer. That is a design decision a bank would actually make.

Deep Agents adds, over a plain ReAct loop: a planning tool, delegation to subagents with
their own context windows, a virtual filesystem for scratch work, and middleware for
summarisation and memory. All four are visible in the trace panel, which is exactly what
makes the reasoning legible on stage rather than a black box.

---

## 2. Composition into the graph

`create_deep_agent(...)` returns a `CompiledStateGraph`, so it composes directly. **Do not
add it as a node object.** Wrap it:

```python
# backend/app/agent/negotiation.py
from deepagents import create_deep_agent

negotiation_agent = create_deep_agent(
    model=get_chat_model(),
    tools=[recalculate_scenario, check_open_finance_assets],
    system_prompt=load_prompt("negotiation"),
    subagents=[POLICY_RESEARCHER, PRECEDENT_ANALYST],
    context_schema=NegotiationCase,
    store=store,
    name="negotiation",
)


def negotiation(state: AgentState, config: RunnableConfig) -> dict:
    """Wrapper: project AgentState in, map the deep agent's result back out."""
    case = NegotiationCase(
        application=state.get("application") or {},
        profile=state.get("profile") or {},
        emit=get_stream_writer(),      # the *parent* graph's writer — see below
    )
    result = _stream_agent(case, _agent_messages(state), config)
    return _map_result(state, result, case)
```

**No `checkpointer=`.** The nested run inherits the parent's through `config`, which is what
puts its checkpoints on the parent thread — verified: they land under
`checkpoint_ns="negotiation:<task>"` with the parent `thread_id`, a fresh namespace per turn.
Passing one explicitly would give the deep agent a checkpoint life of its own.

**`.stream()`, not `.invoke()`.** A subgraph's tokens do not reach the parent's `astream`
([11 §2](11-api-sse.md)), so `.invoke()` would leave the analyst watching a blank screen for
seven seconds and then deliver the whole answer at once. The wrapper streams the agent and
forwards its prose through the parent's writer. No filtering is needed to exclude the
subagents: their tokens never surface at this level at all, because each runs as its own
nested graph inside the `task` tool. That is context isolation being observable.

**Why a wrapper and not a direct subgraph node.** `DeepAgentState` carries `messages`,
`todos` and `files`; `AgentState` carries `calc`, `scenarios`, `decision`, `policies`.
Merging the two schemas would pollute both. The wrapper is ~30 lines and keeps each state
schema meaningful. It is also the seam where scenarios get appended and `pending_approval`
gets set.

Passing the parent `config` through means nested checkpoints land in the same MongoDB thread
namespace — which is a nice thing to point at during the architecture walkthrough.

---

## 3. Tools and subagents

**Main agent tools** — the things it does itself:

```python
recalculate_scenario(down_payment: float | None = None, term_months: int | None = None,
                     amount: float | None = None, annual_rate: float | None = None) -> dict
check_open_finance_assets() -> OpenFinanceAssets
```

Both read the case — application, profile, and the parent's stream writer — from a
`NegotiationCase` passed as LangGraph runtime **context**, injected via `ToolRuntime` and
stripped from the schema the model sees. Hence the signatures above:

- **Every parameter of `recalculate_scenario` is optional and patches the current
  application**, mirroring how `intake` treats a re-simulation ([05 §3](05-graph-nodes-and-routing.md)).
  A turn is usually one lever — *"e se o prazo fosse 420 meses?"* — and a tool demanding all
  four arguments invites the model to restate the other three from memory. Restating is where
  invented numbers come from. `down_payment` wins over `amount` when both arrive: the asset
  value is a fact about the property, the financed amount is its complement.
- **`check_open_finance_assets` takes no `customer_id`.** There is exactly one customer in a
  negotiation and they arrive in context, so the model gets no opportunity to name someone
  else's account. It is also **read-only**: it reports consent, it does not grant it. An agent
  that silently flipped `consent_granted` on a customer's behalf is the first thing a bank's
  risk team would ask about. What it unlocks is an *argument*, which is the demo beat anyway.

`recalculate_scenario` returns `inputs`, the full-precision `calc`, the `domain/rules.py`
`outcome` and `policy_refs` — and a **`resumo`** of pre-formatted Portuguese strings. The
prompt requires quoting `resumo`, because a model handed `0.2889345588` faithfully writes
`0.2889345588`: correct, and unusable on a projector. Formatting is not an instruction the
model may follow; it is a string it can only copy.

**Subagents** — research delegated to isolated context windows:

| Subagent | `name` | Tools | Purpose |
|---|---|---|---|
| Policy researcher | `policy_researcher` | `search_policy` | Finds the applicable policy rules and returns them **with `POL-xxx` citations** |
| Precedent analyst | `precedent_analyst` | `search_precedents` | Finds similar historical cases and summarises how each was decided |

```python
from deepagents import SubAgent

POLICY_RESEARCHER: SubAgent = {
    "name": "policy_researcher",
    "description": "Consulta a política de crédito. Use quando precisar saber se um "
                   "cenário é permitido e sob que condições.",
    "system_prompt": load_prompt("subagent_policy"),
    "tools": [search_policy],
}
```

### Why delegate research instead of calling the tools directly

Policy retrieval returns four full chunks of 80–200 words each; precedent search returns
three case narratives. Injecting all of that into the main loop on every turn floods the
context and degrades the negotiation reasoning by turn three.

A subagent reads the raw chunks in its own window and returns a short, cited conclusion.
That is the actual point of the deep agent pattern — **context isolation**, not "more
agents". Say it that way if asked.

### The separation that matters most

`recalculate_scenario` delegates to `domain/calculator.py`. **The LLM never computes a
number.** The model chooses which scenario to evaluate; deterministic Python evaluates it.
This is the whole answer to *"how do you stop it hallucinating financials?"*, and it is
demonstrable by opening `calculator.py` on stage.

---

## 4. Prompt contract

`backend/app/graph/prompts/negotiation.md` plus one per subagent. Versioned; the version
string is written into every `decisions_log` entry as `prompt_version`.

The main system prompt must:

1. Establish the analyst's role and that **recommendations require human approval**.
2. Require citing policy IDs (`POL-xxx`) for any eligibility claim — sourced from
   `policy_researcher`, not invented.
3. **Forbid asserting any figure not returned by `recalculate_scenario`.** No mental
   arithmetic, no interpolation, no "roughly".
4. Instruct that when Carlos signals a final decision (*"aprovar"*, *"negar"*, *"aprovar com
   condições"*), the agent populates `pending_approval` and stops.
5. Keep responses short. Carlos reads on screen while an audience watches.
6. Use `policy_researcher` before claiming a scenario is or is not permitted; use
   `precedent_analyst` when the case is borderline.

---

## 5. Approval gate

`await_approval` stays a **node in the parent LangGraph**, calling `interrupt()`:

```python
from langgraph.types import interrupt

def await_approval(state: AgentState) -> dict:
    proposal = state["pending_approval"]
    verdict = interrupt(proposal)
    return {"pending_approval": None, "decision": {**proposal, **verdict}}
```

The two are **merged**, not replaced. The proposal carries what the agent argued — the
scenario, the citations, the rationale; the verdict carries what the human ruled. Keeping only
the verdict would leave `persist_decision` unable to write a complete record, and the case
where the two differ is exactly the one an auditor cares about.

`pending_approval` is assembled by the wrapper from data the system already holds, and the
analyst's verdict is detected by keyword rather than by a classifier call — see
`app/agent/proposal.py`. That trade-off is deliberate and stated in that module: it costs no
latency, it cannot hallucinate, and it fails safe, since an unrecognised phrase simply
continues the negotiation. Nothing is written until a human confirms, so the cost of a miss is
one more message.

`deepagents` also offers `interrupt_on={"tool_name": True}` for per-tool human-in-the-loop.
**We deliberately do not use it here**: the approval gate belongs to the parent graph, where
it is visible in the architecture diagram and wired to `POST /api/approve`. Knowing the
alternative exists is good Q&A material — mention it, explain why you chose the other one.

*"Why isn't it fully automatic?"* → because `await_approval` is a graph node with
`interrupt()`. The agent **cannot** write a decision without a human resume. Architecture,
not policy, and visible as a paused step in the trace panel.

---

## 6. ⚠️ Latency risk and the fallback

Deep Agents means more LLM calls per turn: planning, plus one round trip per subagent
delegation. A negotiation turn that would take ~4 s with a plain ReAct loop can take 15 s or
more.

**Fifteen seconds of silence in front of a panel is very long.**

Mitigations, in order:

1. Stream tokens (already in the SSE contract, [11](11-api-sse.md)) so something moves on
   screen immediately.
2. Show subagent delegation as trace steps — waiting is tolerable when the audience can see
   *what* is being waited on. This turns the weakness into the demo's best visual.
3. Cap the main loop's iterations and the subagents' `max_tokens`.
4. Instruct in the prompt that `precedent_analyst` is for borderline cases only, not every turn.

**Fallback, kept behind a config flag:** `AGENT_MODE=deep|react`. The `react` path is a plain
`create_react_agent` with all four tools flat and no subagents. If Wednesday's measured
latency is unacceptable, flip the flag rather than rewrite the node.

Build the deep path first — it is the one you want to present. Add the flag only if
Wednesday's numbers demand it.

### Measured — 2026-08-11, `gpt-5.6-luna`, M10, home network

`scripts/04_measure_negotiation.py` drives `stream_chat_events` itself, so what it times is
the path `/api/chat` runs. Four runs of the full beat-6 sequence (six analyst turns each):

| Run | Median turn | Median turn *with a tool call* | Worst turn | Median first token |
|---|---|---|---|---|
| 1 | 5.0 s | 7.2 s | 8.4 s | 6.1 s |
| 2 | 10.4 s | 12.0 s | 20.4 s | 10.8 s |
| 3 | 6.0 s | 7.0 s | 7.5 s | 5.8 s |
| 4 | 4.8 s | 7.4 s | 10.4 s | 5.7 s |

**Median 4.8–10.4 s, comfortably inside the 15 s budget. §6 is not applied and
`AGENT_MODE` is not built.** Run 2's 20.4 s outlier was a single turn with one tool call —
provider variance, not a code path. Re-run the script on Wednesday and on Friday morning: the
numbers move with the model and with the venue's network, and the fallback is a decision to
make on evidence.

The mitigation that *is* in place is the first one. Tokens stream, and subagent delegation
shows as `trace` steps ([11 §2](11-api-sse.md)) — first token lands at ~6 s while the turn
completes at ~7 s, so the wait is watched rather than blank.

> ⚠️ `LLM_MODEL` is a reasoning model, and Chat Completions **rejects function tools while
> reasoning is on**. `app/llm.py` pins `reasoning_effort="none"`; without it every tool call
> in this file fails with a 400. See [13](13-verified-api-contract.md).

---

## 7. Scenario levers for the demo

The negotiation must be able to move all of these, because these are what Carlos actually
does:

- Reduce the financed amount
- Increase the down payment (drops LTV)
- Extend the term (drops instalment, raises total interest — can breach the age rule)
- Adjust the rate within the analyst's authority (alçada)
- Request Open Finance asset sharing as a mitigant

Rehearse three in sequence for beat 6, ending on Open Finance: it moves the case from "no"
to "yes" for a *business* reason rather than a numeric one.

---

## Acceptance criteria

- [ ] `create_deep_agent` is used with exactly two subagents; the main agent holds only
      `recalculate_scenario` and `check_open_finance_assets`.
- [ ] The wrapper keeps `DeepAgentState` and `AgentState` separate — no `files` or `todos`
      leaking into `AgentState`.
- [ ] Nested checkpoints appear in Atlas under the parent `thread_id`.
- [ ] The agent never states a figure absent from a `recalculate_scenario` result. Verify by
      reading three full transcripts, not by hoping.
- [ ] Every eligibility claim cites a `POL-xxx` id sourced from `policy_researcher`.
- [ ] Subagent delegation is visible as trace steps in the UI.
- [ ] Three consecutive scenarios accumulate in `state["scenarios"]` and render in
      `ScenarioTable`; each writes a `scenario_simulated` entry to `decisions_log`,
      including rejected ones.
- [ ] Saying "aprovar" sets `pending_approval`, reaches `await_approval`, and writes no
      final decision until `/api/approve` is called.
- [x] **Median turn latency measured and recorded** — §6, four runs, median 4.8–10.4 s.
      Re-run `scripts/04_measure_negotiation.py` on Wednesday and Friday morning; if the
      median passes 15 s, apply §6.
