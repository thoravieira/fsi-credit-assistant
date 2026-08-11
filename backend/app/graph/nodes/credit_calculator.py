"""SDD 05 §1 — credit_calculator node. Pure Python: PMT, CET, LTV, DTI. No LLM.

A thin adapter over `domain.calculator.compute_scenario`: it reads the shape of
`AgentState` and hands plain numbers to the domain. The analyst's
`recalculate_scenario` tool calls the same function, so a re-simulation during
negotiation cannot disagree with the simulation the customer already saw.
"""

from app.domain.calculator import compute_scenario
from app.graph.state import AgentState, CalcResult


def credit_calculator(state: AgentState) -> dict:
    application = state["application"]
    profile = state.get("profile") or {}
    credit = profile.get("credit") or {}
    income = profile.get("income") or {}

    calc: CalcResult = compute_scenario(
        product=application["product"],
        asset_value=application["asset_value"],
        financed=application["requested_amount"],
        term_months=application["term_months"],
        # `or 1.0` keeps an unseeded profile from dividing by zero; the DTI it
        # produces is absurd rather than wrong, which is the safe direction —
        # it sends the case to a human instead of auto-approving it.
        net_income=income.get("net_monthly") or 1.0,
        existing_debt=credit.get("existing_monthly_debt", 0.0),
        score=credit.get("internal_score", 650),
    )
    return {"calc": calc}
