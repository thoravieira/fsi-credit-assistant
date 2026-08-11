"""SDD 06 §3 — one retrieval tool per subagent.

These never run in the main agent's context window. A policy query returns four
chunks of 80–200 words and a precedent query returns three case narratives;
injecting that into the main loop on every turn floods it and degrades the
negotiation reasoning by turn three. The subagent reads the raw chunks in its
own window and returns a short, cited conclusion.

**That is the actual point of the deep-agent pattern — context isolation, not
"more agents".** Say it that way if asked.

Neither tool lets the model choose the product filter: it comes from the case
in runtime context, so a mortgage negotiation cannot retrieve an auto-loan
policy no matter what the model types.
"""

from langchain.tools import ToolRuntime, tool
from langchain_core.documents import Document

from app.graph.tools.case import NegotiationCase
from app.retrieval.policies import search_policies
from app.retrieval.precedents import search_precedents as _search_precedents

POLICY_K = 4
PRECEDENT_K = 3


def _hits(docs: list[Document]) -> list[dict]:
    return [{"id": d.metadata.get("_id"), "score": d.metadata.get("score")} for d in docs]


@tool(
    description=(
        "Busca os trechos da política de crédito aplicáveis ao caso. Devolve o texto "
        "integral de cada trecho com o respectivo id POL-xxx para citação."
    )
)
def search_policy(runtime: ToolRuntime[NegotiationCase], query: str) -> str:
    """`$vectorSearch` over `credit_policies`, pre-filtered by product."""
    case = runtime.context
    docs = search_policies(query, case.product, k=POLICY_K)
    case.step("policy_researcher", op="$vectorSearch", collection="credit_policies",
              query=query, k=POLICY_K, hits=_hits(docs))

    if not docs:
        return "Nenhum trecho de política encontrado para esta consulta."
    return "\n\n".join(
        f"[{d.metadata.get('_id')}] {d.metadata.get('title', '')}\n{d.page_content}" for d in docs
    )


@tool(
    description=(
        "Busca casos de crédito semelhantes já decididos. Devolve o resumo, a decisão e a "
        "justificativa de cada um, com o respectivo id CASE-xxxx para citação."
    )
)
def search_precedents(runtime: ToolRuntime[NegotiationCase], query: str) -> str:
    """`$vectorSearch` over `historical_cases`, pre-filtered by product.

    Not filtered by `ltv_band`, though SDD 08 §3 allows it: the corpus is ~60
    cases, and narrowing twice can return one weak match instead of three
    usable ones. On a projector, a thin result set reads worse than a broad one.
    """
    case = runtime.context
    docs = _search_precedents(query, case.product, k=PRECEDENT_K)
    case.step("precedent_analyst", op="$vectorSearch", collection="historical_cases",
              query=query, k=PRECEDENT_K, hits=_hits(docs))

    if not docs:
        return "Nenhum caso histórico semelhante encontrado."
    return "\n\n".join(
        f"[{d.metadata.get('_id')}] decisão: {d.metadata.get('decision')}\n"
        f"{d.page_content}\n"
        f"Justificativa: {d.metadata.get('rationale', '—')}"
        for d in docs
    )
