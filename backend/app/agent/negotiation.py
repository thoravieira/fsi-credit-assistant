"""SDD 06 §2 — the reasoning layer: the only place Deep Agents is used.

Three layers, chosen per problem type rather than by picking the newest tool
for everything: LangChain for conversation, LangGraph for workflow, Deep Agents
here. This node is the one place where the problem is genuinely open-ended —
exploring credit structures under policy constraints — and roughly 90% of
requests never reach it. Drawing the boundary on cost and auditability instead
of on fashion is itself the interview answer.

What Deep Agents adds over a plain ReAct loop is delegation to subagents with
their own context windows. `policy_researcher` reads four full policy chunks
and returns four cited lines; the main loop never sees the raw text. That is
context isolation, and it is why the negotiation still reasons well on turn
three.

## Why a wrapper node, and not the compiled agent as a node

`create_deep_agent()` returns a `CompiledStateGraph`, so it *would* compose
directly. It is wrapped anyway because the two state schemas should not merge:
`DeepAgentState` carries `messages`, `todos` and `files`; `AgentState` carries
`calc`, `scenarios`, `decision`, `policies`. One graph over both pollutes both.

The wrapper is ~40 lines and buys three things: each schema stays meaningful,
the case reaches the tools as runtime context instead of as state, and this is
the seam where deterministic results (`scenarios`) and the human gate
(`pending_approval`) are set.

Passing the parent `config` straight through means the nested run inherits the
parent's checkpointer and `thread_id`; its checkpoints land in Atlas under
`checkpoint_ns="negotiation:<task>"` on the same thread. Verified, not assumed.
"""

from functools import lru_cache

from langchain_core.messages import AIMessage, AIMessageChunk, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer
from langgraph.graph.state import CompiledStateGraph

from deepagents import create_deep_agent

from app.agent.proposal import build_proposal
from app.agent.subagents import POLICY_RESEARCHER, PRECEDENT_ANALYST
from app.audit import append_event
from app.config import DEMO_ANALYST_ID
from app.domain.formatting import brl, percent
from app.graph.prompts import load_prompt
from app.graph.state import AgentState
from app.graph.tools.case import NegotiationCase
from app.graph.tools.scenario import (
    check_open_finance_assets,
    recalculate_scenario,
    solve_for_target_dti,
    solve_term_for_target_dti,
)
from app.llm import get_chat_model
from app.memory.store import get_store


@lru_cache
def get_negotiation_agent() -> CompiledStateGraph:
    """Built once per process, like the parent graph (SDD 04 §4).

    The three tools listed here are the agent's own. `deepagents` also gives it
    a virtual filesystem (`ls`, `read_file`, `write_file`, …) and the `task`
    tool it delegates through — those are the harness, not the domain.

    No `checkpointer=`: the nested run inherits the parent's through `config`,
    which is what puts its checkpoints on the parent thread. `store` is passed
    so the agent's environment matches the parent's.
    """
    return create_deep_agent(
        model=get_chat_model(),
        tools=[
            recalculate_scenario,
            solve_for_target_dti,
            solve_term_for_target_dti,
            check_open_finance_assets,
        ],
        system_prompt=load_prompt("negotiation"),
        subagents=[POLICY_RESEARCHER, PRECEDENT_ANALYST],
        context_schema=NegotiationCase,
        store=get_store(),
        name="negotiation",
    )


def negotiation(state: AgentState, config: RunnableConfig) -> dict:
    """Wrapper node: project `AgentState` in, map the agent's result back out."""
    case = NegotiationCase(
        application=state.get("application") or {},
        profile=state.get("profile") or {},
        # The parent graph's stream writer. A subgraph's own writer does not
        # reach `graph.astream(...)` — see `graph/tools/case.py`.
        emit=get_stream_writer(),
    )

    result = _stream_agent(case, _agent_messages(state), config)
    return _map_result(state, result, case)


def _stream_agent(case: NegotiationCase, messages: list, config: RunnableConfig) -> dict:
    """Run the agent, forwarding its prose as it is written.

    `.invoke()` would be one line shorter. It is not used because a subgraph's
    tokens do not reach the parent's `graph.astream(...)` — the analyst would
    wait in silence for eight seconds and then receive the whole answer at
    once, which is the failure mode SDD 06 §6 exists to prevent.

    Only the main loop's prose is forwarded, and no filtering is needed to
    achieve that: a subagent runs as its own nested graph inside the `task`
    tool, so its tokens never surface at this level at all. The delegation is
    still visible — as a trace step, from the subagent's retrieval tool.
    """
    final: dict = {}
    for mode, chunk in get_negotiation_agent().stream(
        {"messages": messages},
        config=config,  # inherits thread_id -> nested checkpoints in Atlas
        context=case,
        stream_mode=["values", "messages"],
    ):
        if mode == "values":
            final = chunk
            continue
        message_chunk, meta = chunk
        if isinstance(message_chunk, AIMessageChunk) and meta.get("langgraph_node") == "model":
            case.token(_text(message_chunk))
    return final


# --- AgentState in ---------------------------------------------------------


def _agent_messages(state: AgentState) -> list:
    """The conversation the agent sees: a briefing, then the whole thread.

    The whole thread — Mariana's simulation included. `thread_id ==
    application_id` (SDD 04 §1), so Carlos's agent reads the customer's
    conversation with no handoff payload, because it was never in a process's
    memory to begin with.
    """
    return [SystemMessage(_case_briefing(state))] + list(state.get("messages") or [])


def _case_briefing(state: AgentState) -> str:
    """The application, the customer and the assessment that sent the case to a
    human — as text, because that is what a model reads.

    Only inputs and already-decided outputs appear here. Anything the
    negotiation wants to claim about a *new* structure has to come back from
    `recalculate_scenario`.

    Every figure is pre-formatted, for the same reason as the tool's `resumo`:
    a model handed `0.7512` will write `0.7512`, and a raw ratio on a projector
    reads as a bug even when the arithmetic behind it is right.
    """
    application = state.get("application") or {}
    profile = state.get("profile") or {}
    decision = state.get("decision") or {}
    calc = state.get("calc") or {}
    income = profile.get("income") or {}

    lines = [
        "## Situação atual do caso",
        f"- Produto: {application.get('product')}",
        f"- Valor do bem: {brl(application.get('asset_value', 0.0))}",
        f"- Entrada: {brl(application.get('down_payment', 0.0))}",
        f"- Valor financiado: {brl(application.get('requested_amount', 0.0))}",
        f"- Prazo: {application.get('term_months')} meses",
        f"- Cliente: {profile.get('name')}, {(profile.get('employment') or {}).get('type')}, "
        f"renda líquida {brl(income.get('net_monthly', 0.0))}, "
        f"score interno {(profile.get('credit') or {}).get('internal_score')}",
    ]

    # Item 10 — reopening an already-decided case (Carlos browsing the
    # Aprovados/Reprovações tabs) must not read as a live pending decision.
    # `status` comes straight from `applications` (see `_hydrate_application`
    # in main.py), never from checkpoint state, so it's always current even
    # though the graph never runs `decision` again on the analyst path.
    status = application.get("status")
    if status and status not in ("manual_review", "auto_approved"):
        lines.append(
            f"- ATENÇÃO: este caso JÁ FOI DECIDIDO — status atual: {status}. Não é mais uma "
            "decisão pendente. Trate qualquer pedido do analista a partir daqui como "
            "exploração de cenários hipotéticos (entender a dinâmica da aprovação, comparar "
            "com casos parecidos, simular \"e se\"), nunca como uma nova decisão a ser tomada "
            "— não recomende aprovar/negar novamente."
        )
    if calc:
        lines.append(
            f"- Simulação vigente: parcela {brl(calc.get('monthly_payment', 0.0))}, "
            f"LTV {percent(calc.get('ltv', 0.0))}, "
            f"comprometimento de renda {percent(calc.get('dti', 0.0))}, "
            f"taxa anual {percent(calc.get('annual_rate', 0.0))}"
        )
    if decision:
        lines.append(f"- Resultado da análise automática: {decision.get('outcome')}")
        for reason in decision.get("reasons", []):
            lines.append(f"  - {reason}")
        lines.append(f"- Políticas citadas: {', '.join(decision.get('policy_refs', []))}")

    memories = state.get("memories") or []
    if memories:
        lines.append("- Memória de longo prazo sobre a cliente:")
        lines += [f"  - {m.get('content')}" for m in memories if m.get("content")]

    return "\n".join(lines)


# --- agent result out ------------------------------------------------------


def _map_result(state: AgentState, result: dict, case: NegotiationCase) -> dict:
    """Everything that crosses back into `AgentState`, and nothing else.

    Note what does *not* cross: `todos`, `files`, and the agent's tool-call
    messages. Only the final answer, the scenarios `domain/` computed, and — if
    the analyst called for a decision — the proposal for the human gate.

    This node must never write `stage`; the transition to `closed` belongs to
    `persist_decision` (SDD 04 §3).
    """
    answer = _final_text(result)
    _log_scenarios(state, case)

    update: dict = {"messages": [AIMessage(answer)], "scenarios": case.simulated}

    application = state.get("application") or {}
    # Item 10 — a case already decided can't be re-proposed for approval,
    # even if the analyst's exploratory message happens to contain a verdict
    # keyword (e.g. asking "e se eu tivesse aprovado sem condições?"). Belt
    # and suspenders with the frontend disabling the buttons: the backend is
    # the one place this can't be bypassed.
    already_decided = application.get("status") not in (None, "manual_review", "auto_approved")
    proposal = None if already_decided else build_proposal(
        analyst_message=_last_human_text(state),
        agent_message=answer,
        application=application,
        # The recommendation is about a structure that was actually computed:
        # this turn's last scenario, or the last one still in state.
        scenario=(case.simulated or state.get("scenarios") or [None])[-1],
        precedents=state.get("precedents") or [],
    )
    if proposal is not None:
        update["pending_approval"] = proposal
    return update


def _final_text(result: dict) -> str:
    return _text(result["messages"][-1])


def _text(message) -> str:
    content = getattr(message, "content", "")
    return content if isinstance(content, str) else "".join(
        part.get("text", "") for part in content if isinstance(part, dict)
    )


def _last_human_text(state: AgentState) -> str:
    for message in reversed(state.get("messages") or []):
        if getattr(message, "type", None) == "human":
            return str(message.content)
    return ""


def _log_scenarios(state: AgentState, case: NegotiationCase) -> None:
    """SDD 02 §6 — every scenario, including the rejected ones.

    A regulator does not want the final answer; they want the path. The
    structures Carlos discarded are the evidence that there was a process.
    """
    application_id = (state.get("application") or {}).get("application_id")
    if not application_id:
        return
    for scenario in case.simulated:
        append_event(
            application_id,
            "scenario_simulated",
            {"type": "analyst", "id": DEMO_ANALYST_ID},
            inputs=scenario["inputs"],
            calc=scenario["calc"],
            outcome=scenario["outcome"],
            policy_refs=scenario["policy_refs"],
            rationale=" ".join(scenario["reasons"]),
        )
