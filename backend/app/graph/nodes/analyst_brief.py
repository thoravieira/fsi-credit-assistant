"""SDD 05 §1 — analyst_brief node. The case dossier Carlos reads first.

A LangChain node, not an agent: the shape of a dossier is known in advance, so
there is nothing for a reasoning loop to decide. It writes prose over data that
`decision`, `credit_calculator` and `precedent_search` already produced — the
model explains numbers, it does not produce them.

This is the node that sets `stage` to `negotiation` (SDD 04 §3), which is what
routes Carlos's *next* message to the deep agent instead of back here.
"""

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.audit import append_event
from app.config import DEMO_ANALYST_ID
from app.graph.state import AgentState
from app.llm import get_chat_model
from app.runtime_trace import trace_started

_SYSTEM_PROMPT = (
    "Você prepara o dossiê de um caso de crédito para um analista brasileiro. "
    "Escreva em português, no máximo 10 linhas, na ordem: recomendação, os "
    "motivos que levaram o caso à análise manual (com os ids POL-xxx), e os "
    "precedentes relevantes (com os ids CASE-xxxx e como foram decididos). "
    "Use apenas os dados fornecidos — nunca calcule nem estime um número. "
    "Se o contexto indicar que o caso JÁ FOI DECIDIDO, não escreva como se a "
    "decisão estivesse em aberto — resuma o que foi decidido, por quê, e deixe "
    "claro que essa decisão já está registrada, não pendente."
)


def _default_llm() -> BaseChatModel:
    return get_chat_model(temperature=0.2)


def _precedent_lines(precedents: list[dict]) -> str:
    return "\n".join(
        f"- [{p.get('_id')}] decisão: {p.get('decision')} — {p.get('summary', '')}"
        for p in precedents
    )


def analyst_brief(state: AgentState, *, llm: BaseChatModel | None = None) -> dict:
    trace_started("analyst_brief")
    llm = llm or _default_llm()
    application = state.get("application") or {}
    decision = state.get("decision") or {}

    context_lines = [
        f"Pedido: {application}",
        f"Cálculo: {state.get('calc')}",
        f"Decisão automática: {decision}",
        f"Precedentes:\n{_precedent_lines(state.get('precedents') or [])}",
    ]
    # Item 10 — same gap as `negotiation._case_briefing`: a case reopened
    # from the Aprovados/Reprovações tabs (or, for the demo data, opened for
    # the very first time already resolved) must not read as still pending.
    status = application.get("status")
    if status and status not in ("manual_review", "auto_approved"):
        context_lines.append(f"ATENÇÃO: este caso JÁ FOI DECIDIDO — status atual: {status}.")
    context = "\n".join(context_lines)
    response = llm.invoke([SystemMessage(_SYSTEM_PROMPT), HumanMessage(context)])
    text = response.content if isinstance(response.content, str) else str(response.content)

    application_id = application.get("application_id")
    if application_id:
        append_event(
            application_id,
            "recommendation",
            {"type": "agent", "id": "analyst_brief"},
            outcome=decision.get("outcome"),
            policy_refs=decision.get("policy_refs", []),
            precedent_refs=[p["_id"] for p in state.get("precedents") or [] if p.get("_id")],
            rationale=text,
        )

    return {
        "messages": [AIMessage(text, additional_kwargs={"persona": "analyst"})],
        "stage": "negotiation",
    }
