"""SDD 05 §1 + SDD 08 §3 — policy_retrieval node.

Query construction needs an LTV/DTI estimate, but this node runs *before*
`credit_calculator` in the customer-path edges (SDD 05 §2). The estimate
computed here is for the retrieval query only — the official `CalcResult`
that lands in `state.calc` is produced one step later.
"""

from langgraph.config import get_stream_writer

from app.domain.calculator import annual_rate, dti as calc_dti, effective_monthly_rate, ltv as calc_ltv, pmt
from app.graph.state import AgentState
from app.retrieval.policies import search_policies


def policy_retrieval(state: AgentState) -> dict:
    application = state["application"]
    profile = state.get("profile") or {}

    product = application["product"]
    ltv_value = calc_ltv(application["requested_amount"], application["asset_value"])
    score = profile.get("credit", {}).get("internal_score", 650)
    rate = annual_rate(product, ltv_value, score)
    monthly_payment = pmt(
        application["requested_amount"], effective_monthly_rate(rate), application["term_months"]
    )
    net_income = profile.get("income", {}).get("net_monthly") or 1.0
    existing_debt = profile.get("credit", {}).get("existing_monthly_debt", 0.0)
    dti_value = calc_dti(monthly_payment, net_income, existing_debt)
    employment_type = profile.get("employment", {}).get("type", "não informado")

    query = (
        f"{product} com LTV de {ltv_value:.0%}, prazo de {application['term_months']} meses, "
        f"comprometimento de renda de {dti_value:.0%}, cliente {employment_type}"
    )

    writer = get_stream_writer()
    writer({"op": "$vectorSearch", "collection": "credit_policies", "k": 4, "query": query})
    docs = search_policies(query, product, k=4)
    writer({"hits": [{"id": d.metadata.get("_id"), "score": d.metadata.get("score")} for d in docs]})

    return {"policies": [d.metadata | {"text": d.page_content} for d in docs]}
