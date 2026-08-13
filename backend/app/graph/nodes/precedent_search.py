"""SDD 05 §1 + SDD 08 §3 — precedent_search node.

`$vectorSearch` over `historical_cases`, k=3, pre-filtered by product. The
query is a prose description of the case, not a serialisation of its numbers:
cosine similarity between `{"ltv": 0.80}` and `{"ltv": 0.75}` is noise, while
*"autônomo com LTV alto, compensado por relacionamento longo"* carries real
signal (SDD 08 §2). Numbers belong in the pre-filter; prose belongs in the
vector.
"""

from langgraph.config import get_stream_writer

from app.graph.state import AgentState
from app.retrieval.precedents import search_precedents
from app.runtime_trace import trace_started

K = 3


def _case_description(application: dict, profile: dict, calc: dict, decision: dict) -> str:
    employment = (profile.get("employment") or {}).get("type", "não informado")
    reasons = " ".join(decision.get("reasons", []))
    return (
        f"{application.get('product')} de {application.get('requested_amount')} "
        f"em {application.get('term_months')} meses, cliente {employment}, "
        f"LTV de {calc.get('ltv', 0):.0%}, comprometimento de renda de {calc.get('dti', 0):.0%}. "
        f"{reasons}"
    )


def precedent_search(state: AgentState) -> dict:
    trace_started("precedent_search")
    application = state.get("application") or {}
    query = _case_description(
        application, state.get("profile") or {}, state.get("calc") or {}, state.get("decision") or {}
    )

    writer = get_stream_writer()
    writer({"op": "$vectorSearch", "collection": "historical_cases", "k": K, "query": query})
    docs = search_precedents(query, application.get("product", "mortgage"), k=K)
    writer({"hits": [{"id": d.metadata.get("_id"), "score": d.metadata.get("score")} for d in docs]})

    return {"precedents": [d.metadata | {"summary": d.page_content} for d in docs]}
