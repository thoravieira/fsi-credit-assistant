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
    "altera; deixe nulos os campos não mencionados. Nunca invente valores."
)


class _ExtractedFields(BaseModel):
    product: Literal["mortgage", "auto"] | None = None
    asset_value: float | None = None
    down_payment: float | None = None
    requested_amount: float | None = None
    term_months: int | None = None
    purpose: str | None = None


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

    merged = dict(prior)
    for field, value in extracted.model_dump().items():
        if value is not None:
            merged[field] = value

    if (
        merged.get("requested_amount") is None
        and merged.get("asset_value") is not None
        and merged.get("down_payment") is not None
    ):
        merged["requested_amount"] = merged["asset_value"] - merged["down_payment"]

    result: dict = {"application": merged}
    if has_complete_application({"application": merged}) == "complete":
        result["stage"] = "assessment"
    return result
