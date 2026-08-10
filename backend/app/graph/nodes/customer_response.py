"""SDD 05 §1 — customer_response node. Writes Mariana's answer in plain
Portuguese, grounded in `policies` + `calc`. Also handles the "missing
fields" branch when intake could not complete the application.
"""

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.config import get_settings
from app.graph.state import AgentState

_SYSTEM_PROMPT = (
    "Você é a assistente de crédito de um banco brasileiro, respondendo à "
    "cliente em português claro e cordial. Baseie-se apenas nos dados "
    "fornecidos (políticas e cálculo) — nunca invente números ou condições."
)

_REQUIRED_FIELD_LABELS = {
    "product": "tipo de produto (imóvel ou veículo)",
    "asset_value": "valor do bem",
    "down_payment": "valor de entrada",
    "term_months": "prazo em meses",
}


def _default_llm() -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    return ChatOpenAI(model=settings.llm_model, api_key=settings.openai_api_key, temperature=0.3)


def _missing_fields(application: dict | None) -> list[str]:
    application = application or {}
    return [
        label for field, label in _REQUIRED_FIELD_LABELS.items() if application.get(field) is None
    ]


def customer_response(state: AgentState, *, llm: BaseChatModel | None = None) -> dict:
    llm = llm or _default_llm()
    missing = _missing_fields(state.get("application"))

    if missing:
        instruction = "Peça educadamente que a cliente informe os dados que faltam."
        context = f"Campos ainda não informados: {', '.join(missing)}."
    else:
        instruction = (
            "Explique o resultado para a cliente de forma clara, citando a "
            "parcela, a taxa e — se aplicável — os motivos e as políticas "
            "que embasam a decisão."
        )
        context = (
            f"Cálculo: {state.get('calc')}\n"
            f"Decisão: {state.get('decision')}\n"
            f"Políticas citadas: {state.get('policies')}"
        )

    response = llm.invoke(
        [SystemMessage(_SYSTEM_PROMPT), HumanMessage(f"{instruction}\n\n{context}")]
    )
    text = response.content if isinstance(response.content, str) else str(response.content)
    return {"messages": [AIMessage(text)]}
