"""SDD 05 §1 — customer_response node. Writes Mariana's answer in plain
Portuguese, grounded in `policies` + `calc`. Also handles the "missing
fields" branch when intake could not complete the application.
"""

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage

from app.config import get_settings
from app.graph.state import AgentState

_SYSTEM_PROMPT = (
    "Você é a assistente de crédito de um banco brasileiro, respondendo à "
    "cliente em português claro e cordial. Baseie-se apenas nos dados "
    "fornecidos (políticas e cálculo) — nunca invente números ou condições. "
    "Responda diretamente à pergunta da cliente, transcrita abaixo — se ela "
    "pediu um mínimo, um máximo, ou perguntou sobre um cenário diferente do "
    "anterior, a resposta deve deixar claro que esse pedido específico foi "
    "atendido, não repetir a explicação da simulação anterior como se nada "
    "tivesse mudado."
)

_REQUIRED_FIELD_LABELS = {
    "product": "tipo de produto (imóvel ou veículo)",
    "asset_value": "valor do bem",
    "down_payment": "valor de entrada",
    "term_months": "prazo em meses",
    "purpose": "finalidade (ex.: compra, reforma, troca)",
}


def _default_llm() -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    return ChatOpenAI(model=settings.llm_model, api_key=settings.openai_api_key, temperature=0.3)


def _missing_fields(application: dict | None) -> list[str]:
    application = application or {}
    return [label for field, label in _REQUIRED_FIELD_LABELS.items() if not application.get(field)]


def _last_human_text(messages: list[AnyMessage]) -> str:
    for message in reversed(messages):
        if getattr(message, "type", None) == "human":
            content = message.content
            return content if isinstance(content, str) else str(content)
    return ""


def customer_response(state: AgentState, *, llm: BaseChatModel | None = None) -> dict:
    llm = llm or _default_llm()
    missing = _missing_fields(state.get("application"))
    question = _last_human_text(state.get("messages") or [])

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
            f"Pergunta/mensagem da cliente nesta rodada: {question!r}\n"
            f"Cálculo: {state.get('calc')}\n"
            f"Decisão: {state.get('decision')}\n"
            f"Políticas citadas: {state.get('policies')}"
        )

    response = llm.invoke(
        [SystemMessage(_SYSTEM_PROMPT), HumanMessage(f"{instruction}\n\n{context}")]
    )
    text = response.content if isinstance(response.content, str) else str(response.content)
    return {"messages": [AIMessage(text)]}
