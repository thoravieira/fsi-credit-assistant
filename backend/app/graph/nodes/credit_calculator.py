"""SDD 05 §1 — credit_calculator node. Pure Python: PMT, CET, LTV, DTI. No LLM."""

from app.domain.calculator import (
    annual_rate,
    cet_annual,
    dti as calc_dti,
    effective_monthly_rate,
    ltv as calc_ltv,
    pmt,
    schedule_preview,
)
from app.graph.state import AgentState, CalcResult

# Illustrative transaction-cost assumptions feeding `cet_annual`. These are
# not policy thresholds, so they are not subject to the policy/code
# consistency invariant in SDD 10 §4.
MONTHLY_INSURANCE_RATE = 0.00025  # MIP/DFI, % of financed amount per month
APPRAISAL_FEE = 2_500.0
IOF_RATE = 0.0038


def credit_calculator(state: AgentState) -> dict:
    application = state["application"]
    profile = state.get("profile") or {}

    product = application["product"]
    financed = application["requested_amount"]
    asset_value = application["asset_value"]
    n = application["term_months"]

    ltv_value = calc_ltv(financed, asset_value)
    score = profile.get("credit", {}).get("internal_score", 650)
    rate = annual_rate(product, ltv_value, score)
    monthly_rate = effective_monthly_rate(rate)

    monthly_payment = pmt(financed, monthly_rate, n)
    total_interest = monthly_payment * n - financed

    net_income = profile.get("income", {}).get("net_monthly") or 1.0
    existing_debt = profile.get("credit", {}).get("existing_monthly_debt", 0.0)
    dti_value = calc_dti(monthly_payment, net_income, existing_debt)

    cet = cet_annual(
        principal=financed,
        monthly_payment=monthly_payment,
        n=n,
        monthly_insurance=financed * MONTHLY_INSURANCE_RATE,
        appraisal_fee=APPRAISAL_FEE,
        iof=financed * IOF_RATE,
    )

    calc: CalcResult = {
        "monthly_payment": monthly_payment,
        "total_interest": total_interest,
        "annual_rate": rate,
        "cet_annual": cet,
        "ltv": ltv_value,
        "dti": dti_value,
        "schedule_preview": schedule_preview(financed, monthly_rate, n),
    }
    return {"calc": calc}
