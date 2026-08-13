"""SDD 05 §1 — intake node. Extracts/normalises loan parameters from free
text into `CreditApplication`, patching the fields the message actually
changes rather than re-asking for everything (SDD 05, "why customer turns
always route to intake"). Leaves missing fields `None`.
"""

from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from app.config import get_settings
from app.graph.routing import has_complete_application
from app.graph.state import AgentState

_SYSTEM_PROMPT = (
    "Você extrai parâmetros de um pedido de crédito a partir de mensagens em "
    "português. Preencha apenas os campos que a mensagem realmente informa ou "
    "altera; deixe nulos os campos não mencionados. Nunca invente valores.\n\n"
    "Além disso, classifique a intenção em `intent` — a cliente pode pedir para "
    "resolver QUALQUER uma das três variáveis do financiamento, mantendo as "
    "outras duas fixas:\n"
    "- 'solve_financed': pergunta o valor MÁXIMO de financiamento/crédito ou o "
    "valor máximo do imóvel/veículo que consegue, dado um valor de entrada "
    "(ex.: \"qual o máximo que eu consigo pré-aprovado dando X de entrada?\"). "
    "A entrada é o dado fixo; o financiamento/valor do bem é a incógnita.\n"
    "- 'solve_down_payment': pergunta a MENOR entrada que precisa dar, mantendo "
    "o mesmo valor do imóvel/veículo e prazo (ex.: \"qual a menor entrada para "
    "o mesmo valor e prazo?\"). O valor do bem e o prazo são fixos; a entrada é "
    "a incógnita.\n"
    "- 'solve_term_min': pergunta o prazo MÍNIMO que consegue, mantendo os "
    "mesmos valores de entrada e financiamento.\n"
    "- 'solve_term_max': pergunta o prazo MÁXIMO que consegue, mantendo os "
    "mesmos valores de entrada e financiamento.\n"
    "- 'update': qualquer outra mensagem, incluindo quando a cliente informa um "
    "novo valor de imóvel/veículo, entrada ou prazo para recalcular normalmente "
    "(não uma pergunta sobre limite mínimo/máximo)."
)


class _ExtractedFields(BaseModel):
    product: Literal["mortgage", "auto"] | None = None
    asset_value: float | None = None
    down_payment: float | None = None
    requested_amount: float | None = None
    term_months: int | None = None
    purpose: str | None = None
    intent: Literal["update", "solve_financed", "solve_down_payment", "solve_term_min", "solve_term_max"] = "update"


# Which fields must already be known (product + purpose are always required —
# see `has_complete_application`/`customer_response._REQUIRED_FIELD_LABELS`)
# before a solve is attempted for a given intent, beyond that base set. If
# they're missing, intake falls through to plain `update` and the ordinary
# "faltam dados" branch asks for them instead of guessing (SDD 12 follow-up,
# item 2 — "faça perguntas adicionais para ter todos os 4 dados").
_SOLVE_REQUIRES: dict[str, tuple[str, ...]] = {
    "solve_financed": ("down_payment", "term_months"),
    "solve_down_payment": ("asset_value", "term_months"),
    "solve_term_min": ("asset_value", "down_payment"),
    "solve_term_max": ("asset_value", "down_payment"),
}


def _default_llm() -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    return ChatOpenAI(model=settings.llm_model, api_key=settings.openai_api_key, temperature=0)


def _last_human_text(messages: list[AnyMessage]) -> str:
    for message in reversed(messages):
        if getattr(message, "type", None) == "human":
            return message.content
    return ""


def intake(state: AgentState, *, llm: BaseChatModel | None = None) -> dict:
    llm = llm or _default_llm()
    prior = dict(state.get("application") or {})
    text = _last_human_text(state["messages"])

    extracted = llm.with_structured_output(_ExtractedFields).invoke(
        [
            SystemMessage(_SYSTEM_PROMPT),
            HumanMessage(f"Dados já conhecidos: {prior}\nMensagem do cliente: {text}"),
        ]
    )

    fields = extracted.model_dump()
    intent = fields.pop("intent", "update")
    merged = dict(prior)
    for field, value in fields.items():
        if value is not None:
            merged[field] = value

    # A "qual o mínimo/máximo…" question is not a request to patch a field
    # with whatever old figure is still attached — it's a request to solve
    # for one of the three numbers, holding the other two fixed. Flagging it
    # here (instead of computing it here) keeps intake as pure extraction:
    # `credit_calculator` has the customer's profile (income, score, existing
    # debt) that solving actually needs, and intake runs before
    # `load_context` fetches it (SDD 05 §1 node order). `_intent` never
    # survives past that node — `credit_calculator` pops it either way.
    required = _SOLVE_REQUIRES.get(intent)
    if required and all(merged.get(f) is not None for f in required) and merged.get("purpose"):
        merged["_intent"] = intent
    else:
        merged.pop("_intent", None)
        # Re-derive the financed amount unless *this turn* stated one explicitly.
        # Keying off `merged` instead would pin `requested_amount` to whatever the
        # first turn computed, so "e se eu desse mais entrada?" would change the
        # down payment and leave the financed amount — and therefore the LTV, the
        # instalment and the decision — untouched. That re-simulation is the whole
        # reason customer turns always route back here (SDD 05 §3).
        if (
            fields.get("requested_amount") is None
            and merged.get("asset_value") is not None
            and merged.get("down_payment") is not None
        ):
            merged["requested_amount"] = merged["asset_value"] - merged["down_payment"]

    result: dict = {"application": merged}
    if has_complete_application({"application": merged}) == "complete":
        result["stage"] = "assessment"
    return result
