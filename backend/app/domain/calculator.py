"""SDD 10 §2 — credit arithmetic. Zero LLM involvement, zero LangChain imports.

All money values are `float` in this demo. Production would use `Decimal` or
integer cents to avoid binary floating-point rounding in financial output.
"""

from typing import Literal

Product = Literal["mortgage", "auto"]

# SDD 10 §2: monthly-rate conversion must be *effective*, not nominal
# (annual / 12). Nominal conversion is the single most common error in
# Brazilian credit code.
def effective_monthly_rate(annual_rate_value: float) -> float:
    return (1 + annual_rate_value) ** (1 / 12) - 1


def pmt(pv: float, monthly_rate: float, n: int) -> float:
    """Tabela Price fixed installment: PV * i / (1 - (1+i)**-n)."""
    return pv * monthly_rate / (1 - (1 + monthly_rate) ** -n)


def ltv(financed: float, asset_value: float) -> float:
    return financed / asset_value


def dti(monthly_payment: float, net_income: float, existing_debt: float) -> float:
    return (monthly_payment + existing_debt) / net_income


# Rate tables transcribed verbatim from POL-018 (mortgage) and POL-019 (auto).
# Combinations outside the tabled bands have no automatic rate per policy —
# "dependem de aprovação manual com taxa definida caso a caso pelo comitê de
# crédito" — so this returns the widest tabled spread as a display placeholder
# for those cases, never a real committee-set rate.
def annual_rate(product: Product, ltv_value: float, score: int) -> float:
    if product == "mortgage":
        base = 0.098
        if ltv_value <= 0.60 and score >= 750:
            return base
        if ltv_value <= 0.80 and score >= 750:
            return base + 0.008
        if ltv_value <= 0.80 and score >= 650:
            return base + 0.015
        return base + 0.025

    base = 0.145
    if ltv_value <= 0.70 and score >= 700:
        return base
    if ltv_value <= 0.90 and score >= 700:
        return base + 0.012
    if ltv_value <= 0.90 and score >= 600:
        return base + 0.025
    return base + 0.025


def cet_annual(
    principal: float,
    monthly_payment: float,
    n: int,
    *,
    monthly_insurance: float = 0.0,
    appraisal_fee: float = 0.0,
    iof: float = 0.0,
    tol: float = 1e-7,
    max_iter: int = 200,
) -> float:
    """IRR of the full cash flow (principal net of upfront fees vs. monthly
    outflow of installment + insurance), annualised. Bisection over the
    annual rate in [0, 2.0] per SDD 10 §2 — not Newton's method, which can
    diverge on irregular cash flows.
    """
    net_proceeds = principal - appraisal_fee - iof
    monthly_outflow = monthly_payment + monthly_insurance

    def npv(annual: float) -> float:
        r = effective_monthly_rate(annual)
        if r == 0:
            return net_proceeds - monthly_outflow * n
        return net_proceeds - monthly_outflow * (1 - (1 + r) ** -n) / r

    lo, hi = 0.0, 2.0
    f_lo = npv(lo)
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        f_mid = npv(mid)
        if abs(f_mid) < tol or (hi - lo) / 2 < tol:
            return mid
        if (f_mid < 0) == (f_lo < 0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
    return (lo + hi) / 2


def max_financeable(
    *,
    product: Product,
    down_payment: float,
    term_months: int,
    net_income: float,
    dti_limit: float,
    ltv_limit: float,
    amount_limit: float,
    existing_debt: float = 0.0,
    score: int = 650,
    tol: float = 1.0,
    max_iter: int = 60,
) -> float:
    """Largest `financed` for which LTV, DTI and the amount alçada all clear —
    the inverse of the usual "asset value in, decision out" direction: here
    the customer gives a down payment and asks for the ceiling, not a
    specific property (SDD 12 follow-up, item 2 — "simulação inversa").

    Solved by bisection, not algebra, because `annual_rate` is a step
    function of LTV (SDD 10 §3), which is itself a function of the unknown
    `financed` — same technique as `cet_annual`, same reason: no closed form
    once the rate depends on the answer. `down_payment` is a fact about
    resources on hand, not about a property already chosen, so
    `asset_value = financed + down_payment` here — financed and down payment
    always sum to the asset value being implicitly proposed.
    """

    def _dti_ltv(financed: float) -> tuple[float, float]:
        asset_value = financed + down_payment
        ltv_value = ltv(financed, asset_value) if asset_value > 0 else 0.0
        annual = annual_rate(product, ltv_value, score)
        monthly_rate = effective_monthly_rate(annual)
        payment = pmt(financed, monthly_rate, term_months) if financed > 0 else 0.0
        return dti(payment, net_income, existing_debt), ltv_value

    def _clears(financed: float) -> bool:
        d, l = _dti_ltv(financed)
        return d <= dti_limit and l <= ltv_limit

    lo, hi = 0.0, amount_limit
    if _clears(hi):
        return hi
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        if _clears(mid):
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return lo


def max_financeable_fixed_asset(
    *,
    product: Product,
    asset_value: float,
    term_months: int,
    net_income: float,
    dti_limit: float,
    ltv_limit: float,
    amount_limit: float,
    existing_debt: float = 0.0,
    score: int = 650,
    tol: float = 1.0,
    max_iter: int = 60,
) -> float:
    """Largest `financed` for a *fixed* `asset_value` — the sibling inverse of
    `max_financeable`: "menor entrada para o mesmo valor e prazo" fixes the
    property and the term and asks for the ceiling on the loan (item 2
    follow-up). `asset_value` does not move here, unlike `max_financeable`
    where it's derived from the unknown financed amount — so LTV is a plain
    ratio against a constant, and only DTI still needs the bisection (the
    rate band is still a step function of the resulting LTV).

    `down_payment_min = asset_value - max_financeable_fixed_asset(...)`.
    """

    def _dti_ltv(financed: float) -> tuple[float, float]:
        ltv_value = ltv(financed, asset_value) if asset_value > 0 else 0.0
        annual = annual_rate(product, ltv_value, score)
        monthly_rate = effective_monthly_rate(annual)
        payment = pmt(financed, monthly_rate, term_months) if financed > 0 else 0.0
        return dti(payment, net_income, existing_debt), ltv_value

    def _clears(financed: float) -> bool:
        d, l = _dti_ltv(financed)
        return d <= dti_limit and l <= ltv_limit

    lo, hi = 0.0, min(amount_limit, asset_value)
    if _clears(hi):
        return hi
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        if _clears(mid):
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return lo


def term_bounds(
    *,
    product: Product,
    asset_value: float,
    financed: float,
    net_income: float,
    dti_limit: float,
    ltv_limit: float,
    amount_limit: float,
    age_limit: float,
    current_age_years: float | None,
    existing_debt: float = 0.0,
    score: int = 650,
    min_search_term: int = 1,
    max_search_term: int = 600,
) -> dict:
    """The feasible term range for a *fixed* asset value and financed amount —
    "qual o prazo mínimo/máximo" (item 2 follow-up). LTV and the amount
    alçada don't depend on term at all, so they're checked once: if either
    already breaks, no term fixes it (`feasible=False`) — this is the
    "reduza o valor financiado" case shown through the term door instead.

    With LTV fixed, `annual_rate` doesn't change across the search, so
    `pmt(financed, rate, n)` — and therefore DTI — is strictly decreasing in
    `n`. That monotonicity is what makes both bounds well-defined:
    `min_term` is the shortest term whose DTI still clears (a longer term
    only ever helps DTI, never hurts it), and `max_term` is capped by
    POL-006/007's age-plus-term limit alone, since DTI never becomes the
    binding constraint again past `min_term`. No birth date on file means no
    max term can be confirmed — same "absence of evidence is not evidence of
    a pass" rule as `domain/rules.py`.
    """
    ltv_value = ltv(financed, asset_value) if asset_value > 0 else 0.0
    if ltv_value > ltv_limit or financed > amount_limit:
        return {"feasible": False, "reason": "ltv_or_amount", "min_term": None, "max_term": None}

    annual = annual_rate(product, ltv_value, score)
    monthly_rate = effective_monthly_rate(annual)

    def _dti_at(term_months: int) -> float:
        payment = pmt(financed, monthly_rate, term_months) if financed > 0 else 0.0
        return dti(payment, net_income, existing_debt)

    if _dti_at(max_search_term) > dti_limit:
        return {"feasible": False, "reason": "dti_unreachable", "min_term": None, "max_term": None}

    lo, hi = min_search_term, max_search_term
    if _dti_at(lo) <= dti_limit:
        min_term = lo
    else:
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if _dti_at(mid) <= dti_limit:
                hi = mid
            else:
                lo = mid
        min_term = hi

    if current_age_years is None:
        return {"feasible": False, "reason": "birth_date_missing", "min_term": min_term, "max_term": None}
    max_term = int((age_limit - current_age_years) * 12)
    if max_term < min_term:
        return {"feasible": False, "reason": "age_conflicts_with_dti", "min_term": min_term, "max_term": max_term}
    return {"feasible": True, "reason": None, "min_term": min_term, "max_term": max_term}


def schedule_preview(pv: float, monthly_rate: float, n: int) -> list[dict]:
    """First 2 and last 1 amortisation rows of the Tabela Price schedule."""
    payment = pmt(pv, monthly_rate, n)
    balance = pv
    rows = []
    for installment in range(1, n + 1):
        interest = balance * monthly_rate
        amortization = payment - interest
        balance -= amortization
        rows.append(
            {
                "installment": installment,
                "payment": payment,
                "interest": interest,
                "amortization": amortization,
                "balance": max(balance, 0.0),
            }
        )
    return rows[:2] + rows[-1:]


# Illustrative transaction-cost assumptions feeding `cet_annual`. Not policy
# thresholds, so not subject to the policy/code consistency invariant of
# SDD 10 §4.
MONTHLY_INSURANCE_RATE = 0.00025  # MIP/DFI, % of financed amount per month
APPRAISAL_FEE = 2_500.0
IOF_RATE = 0.0038


def compute_scenario(
    *,
    product: Product,
    asset_value: float,
    financed: float,
    term_months: int,
    net_income: float,
    existing_debt: float = 0.0,
    score: int = 650,
    rate: float | None = None,
) -> dict:
    """One credit structure, fully evaluated. Returns the `CalcResult` shape of
    SDD 04 §2 as a plain dict — `domain/` imports neither `langchain*` nor
    `langgraph*`, so it cannot name the TypedDict.

    Both paths through the system call this and nothing else: the
    `credit_calculator` node on Mariana's side, and the `recalculate_scenario`
    tool on Carlos's. That is deliberate. If the analyst's re-simulation used
    a second implementation, the two screens could disagree by a few reais on
    stage and there would be no good answer for why.

    `rate=None` means "apply the tabled rate for this LTV and score". Passing a
    rate is the analyst exercising their authority (alçada), which is one of
    the negotiation levers in SDD 06 §7.
    """
    ltv_value = ltv(financed, asset_value)
    annual = annual_rate(product, ltv_value, score) if rate is None else rate
    monthly_rate = effective_monthly_rate(annual)

    monthly_payment = pmt(financed, monthly_rate, term_months)

    return {
        "monthly_payment": monthly_payment,
        "total_interest": monthly_payment * term_months - financed,
        "annual_rate": annual,
        "cet_annual": cet_annual(
            principal=financed,
            monthly_payment=monthly_payment,
            n=term_months,
            monthly_insurance=financed * MONTHLY_INSURANCE_RATE,
            appraisal_fee=APPRAISAL_FEE,
            iof=financed * IOF_RATE,
        ),
        "ltv": ltv_value,
        "dti": dti(monthly_payment, net_income, existing_debt),
        "schedule_preview": schedule_preview(financed, monthly_rate, term_months),
    }
