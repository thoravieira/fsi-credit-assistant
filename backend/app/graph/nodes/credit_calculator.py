"""SDD 05 §1 — credit_calculator node. Pure Python: PMT, CET, LTV, DTI. No LLM.

A thin adapter over `domain.calculator.compute_scenario`: it reads the shape of
`AgentState` and hands plain numbers to the domain. The analyst's
`recalculate_scenario` tool calls the same function, so a re-simulation during
negotiation cannot disagree with the simulation the customer already saw.
"""

from datetime import date

from app.domain.calculator import (
    compute_scenario,
    max_financeable,
    max_financeable_fixed_asset,
    max_term_by_age,
    term_bounds,
)
from app.domain.rules import POLICIES, age_at_maturity
from app.graph.state import AgentState, CalcResult


def _solve_financed(application: dict, policy, net_income: float, existing_debt: float, score: int) -> None:
    """"Qual o máximo que eu consigo dando X de entrada?" — down payment and
    term are fixed; `asset_value = financed + down_payment` is implied, not
    given. "pré-aprovado" means clearing the *auto-approval* band (POL-020/
    021), so this — like the other three solves below — always targets that
    band, never the wider manual-review one.
    """
    financed = max_financeable(
        product=application["product"],
        down_payment=application["down_payment"],
        term_months=application["term_months"],
        net_income=net_income,
        existing_debt=existing_debt,
        score=score,
        dti_limit=policy.dti_auto_approval_limit.value,
        ltv_limit=policy.ltv_auto_approval_limit.value,
        amount_limit=policy.amount_auto_approval_limit.value,
    )
    application["requested_amount"] = financed
    application["asset_value"] = financed + application["down_payment"]


def _solve_down_payment(application: dict, policy, net_income: float, existing_debt: float, score: int) -> None:
    """"Qual a menor entrada para o mesmo valor e prazo?" — asset value and
    term are fixed; the down payment (and therefore the financed amount)
    move.
    """
    financed = max_financeable_fixed_asset(
        product=application["product"],
        asset_value=application["asset_value"],
        term_months=application["term_months"],
        net_income=net_income,
        existing_debt=existing_debt,
        score=score,
        dti_limit=policy.dti_auto_approval_limit.value,
        ltv_limit=policy.ltv_auto_approval_limit.value,
        amount_limit=policy.amount_auto_approval_limit.value,
    )
    application["requested_amount"] = financed
    application["down_payment"] = application["asset_value"] - financed


def _solve_financed_max_term(application: dict, policy, profile: dict, net_income: float, existing_debt: float, score: int) -> None:
    """"Qual o valor máximo que eu consigo financiar, com o prazo máximo?" — a
    compound ask: down payment is fixed, but unlike `_solve_financed`, the
    term is *not* a fact already sitting on the application either — it must
    resolve to POL-006/007's age-derived ceiling first, never to whatever
    `term_months` happens to still be in state (a stale prior turn, or the
    frontend form's default). Once the true max term is known, `financed`
    solves exactly like `_solve_financed` at that term. Leaves `application`
    untouched with no birth date on file — same "absence of evidence is not
    evidence of a pass" rule as `_solve_term`.
    """
    current_age = age_at_maturity(profile.get("birth_date"), 0, date.today())
    if current_age is None:
        return
    max_term = max_term_by_age(policy.age_at_maturity_limit.value, current_age)
    if max_term <= 0:
        return
    application["term_months"] = max_term
    financed = max_financeable(
        product=application["product"],
        down_payment=application["down_payment"],
        term_months=max_term,
        net_income=net_income,
        existing_debt=existing_debt,
        score=score,
        dti_limit=policy.dti_auto_approval_limit.value,
        ltv_limit=policy.ltv_auto_approval_limit.value,
        amount_limit=policy.amount_auto_approval_limit.value,
    )
    application["requested_amount"] = financed
    application["asset_value"] = financed + application["down_payment"]


def _solve_term(application: dict, policy, profile: dict, net_income: float, existing_debt: float, score: int, *, want: str) -> None:
    """"Qual o prazo mínimo/máximo para os mesmos valores de entrada e
    financiamento?" — asset value and financed amount are fixed; only the
    term moves. Silently leaves `application` untouched when infeasible
    (LTV/amount already breaks regardless of term, no birth date on file, or
    the DTI-driven minimum term outlives the age-driven maximum) — the
    unmodified scenario's own real LTV/DTI/age reasons are the honest answer
    in that case, not a guessed term.
    """
    bounds = term_bounds(
        product=application["product"],
        asset_value=application["asset_value"],
        financed=application["requested_amount"],
        net_income=net_income,
        existing_debt=existing_debt,
        score=score,
        dti_limit=policy.dti_auto_approval_limit.value,
        ltv_limit=policy.ltv_auto_approval_limit.value,
        amount_limit=policy.amount_auto_approval_limit.value,
        age_limit=policy.age_at_maturity_limit.value,
        current_age_years=age_at_maturity(profile.get("birth_date"), 0, date.today()),
    )
    if not bounds["feasible"]:
        return
    application["term_months"] = bounds["min_term" if want == "min" else "max_term"]


_SOLVERS = {
    "solve_financed": _solve_financed,
    "solve_down_payment": _solve_down_payment,
}


def credit_calculator(state: AgentState) -> dict:
    application = dict(state["application"])
    profile = state.get("profile") or {}
    credit = profile.get("credit") or {}
    income = profile.get("income") or {}
    net_income = income.get("net_monthly") or 1.0
    existing_debt = credit.get("existing_monthly_debt", 0.0)
    score = credit.get("internal_score", 650)

    result: dict = {}

    # "Simulação inversa" (item 2): `intake` flagged which of the three
    # numbers this turn asks to solve for, and stashed the customer's
    # profile-dependent unknowns for here — the first node in the customer
    # path that actually has `profile` loaded (SDD 05 §1 order). `_intent`
    # never survives past this node either way.
    intent = application.pop("_intent", None)
    solver = _SOLVERS.get(intent)
    if solver or intent in ("solve_term_min", "solve_term_max", "solve_financed_max_term"):
        policy = POLICIES[application["product"]]
        if solver:
            solver(application, policy, net_income, existing_debt, score)
        elif intent == "solve_financed_max_term":
            _solve_financed_max_term(application, policy, profile, net_income, existing_debt, score)
        else:
            _solve_term(application, policy, profile, net_income, existing_debt, score, want=intent.removeprefix("solve_term_"))
        result["application"] = application

    calc: CalcResult = compute_scenario(
        product=application["product"],
        asset_value=application["asset_value"],
        financed=application["requested_amount"],
        term_months=application["term_months"],
        # `or 1.0` keeps an unseeded profile from dividing by zero; the DTI it
        # produces is absurd rather than wrong, which is the safe direction —
        # it sends the case to a human instead of auto-approving it.
        net_income=net_income,
        existing_debt=existing_debt,
        score=score,
    )
    result["calc"] = calc
    return result
