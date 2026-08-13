"""SDD 06 §3 — the two tools the main negotiation agent holds itself.

**This file is the answer to "how do you stop it hallucinating financials?"**
The model picks which structure to try; `domain/` evaluates it and `domain/`
decides whether it clears policy. Neither tool asks the model for a number it
did not already have, and neither returns a number the model produced.

The `description=` on each tool is what the LLM reads; the Python docstring is
what a reader reads. Keeping them separate is why the model-facing text is
Portuguese while the module stays English (CLAUDE.md).
"""

from datetime import date

from langchain.tools import ToolRuntime, tool

from app.domain.calculator import (
    compute_scenario,
    max_financeable,
    max_financeable_fixed_asset,
    max_term_by_age,
    term_bounds,
)
from app.domain.formatting import brl, percent
from app.domain.rules import POLICIES, age_at_maturity, evaluate
from app.graph.tools.case import NegotiationCase


@tool(
    description=(
        "Recalcula o cenário de crédito e devolve os números oficiais (parcela, LTV, CET, "
        "comprometimento de renda) junto com a avaliação de política. Informe apenas os "
        "parâmetros que mudam em relação ao pedido atual; os demais são mantidos. "
        "Use esta ferramenta sempre que precisar citar qualquer valor."
    )
)
def recalculate_scenario(
    runtime: ToolRuntime[NegotiationCase],
    down_payment: float | None = None,
    term_months: int | None = None,
    amount: float | None = None,
    annual_rate: float | None = None,
) -> dict:
    """Evaluate one credit structure against the case in runtime context.

    Every parameter is optional and patches the current application, mirroring
    how `intake` treats a customer's re-simulation (SDD 05 §3). A negotiation
    turn is usually one lever — *"e se o prazo fosse 420 meses?"* — and a tool
    that demanded all four arguments would invite the model to restate the
    other three from memory. Restating is where invented numbers come from.

    `down_payment` and `amount` are the same lever seen from two sides, so the
    entrada wins when both are given: the asset value is a fact about the
    property, and the financed amount is its complement.

    `annual_rate` is the analyst exercising their authority (alçada). Left
    unset, the tabled rate for the resulting LTV and score applies.

    This tool only *evaluates a guess* — it cannot answer "what financed
    amount hits exactly 32% de comprometimento de renda?" without the model
    interpolating `down_payment`/`amount` itself, which Rule 1 in the
    negotiation prompt forbids. `solve_for_target_dti` exists for that case.
    """
    case = runtime.context
    application = case.application
    profile = case.profile

    asset_value = float(application["asset_value"])
    if down_payment is not None:
        financed = asset_value - float(down_payment)
    elif amount is not None:
        financed = float(amount)
    else:
        financed = float(application["requested_amount"])
    term = int(term_months if term_months is not None else application["term_months"])

    return _simulate(
        case, application, profile, financed=financed, term=term, rate=annual_rate, tool_name="recalculate_scenario"
    )


@tool(
    description=(
        "Resolve o valor financiado (e a entrada correspondente) para atingir um "
        "comprometimento de renda (DTI) alvo, mantendo o valor do bem e o prazo fixos — "
        "devolve os números oficiais já avaliados pela política, sem aproximação. Use esta "
        "ferramenta em vez de `recalculate_scenario` sempre que Carlos pedir um percentual de "
        "comprometimento de renda específico (ex.: \"reduzindo o comprometimento para 32%, "
        "quanto fica o financiamento?\"), em vez de tentar valores de entrada por tentativa."
    )
)
def solve_for_target_dti(
    runtime: ToolRuntime[NegotiationCase],
    dti_target: float,
    term_months: int | None = None,
    keep_down_payment: bool = False,
) -> dict:
    """The exact inverse of `recalculate_scenario` for a target DTI.

    Wraps `domain.calculator.max_financeable_fixed_asset` — the same bisection
    `credit_calculator` uses for the customer's own inverse simulations — so
    the model gets the financed amount that actually clears `dti_target`
    instead of guessing a `down_payment`/`amount` and checking the result
    turn after turn.

    By default `asset_value` never moves, the same invariant as
    `recalculate_scenario`; the down payment is its complement. With
    `keep_down_payment=True`, the down payment and term stay fixed instead,
    and the implied asset value moves together with the financed amount.

    `ltv_limit=1.0` deliberately leaves LTV unconstrained here: the DTI target
    is the only thing being solved for, and the resulting LTV is reported
    (and evaluated against policy) rather than capped mid-bisection.
    """
    case = runtime.context
    application = case.application
    profile = case.profile
    credit = profile.get("credit") or {}
    income = profile.get("income") or {}

    target = _normalize_ratio(dti_target)
    asset_value = float(application["asset_value"])
    term = int(term_months if term_months is not None else application["term_months"])

    common = {
        "product": application["product"],
        "term_months": term,
        "net_income": income.get("net_monthly") or 1.0,
        "existing_debt": credit.get("existing_monthly_debt", 0.0),
        "score": credit.get("internal_score", 650),
        "dti_limit": target,
        "ltv_limit": 1.0,
    }
    if keep_down_payment:
        financed = max_financeable(
            down_payment=float(application["down_payment"]),
            amount_limit=POLICIES[application["product"]].amount_manual_approval_limit.value,
            **common,
        )
        asset_value = financed + float(application["down_payment"])
    else:
        financed = max_financeable_fixed_asset(
            asset_value=asset_value, amount_limit=asset_value, **common
        )

    scenario = _simulate(
        case,
        application,
        profile,
        financed=financed,
        term=term,
        rate=None,
        asset_value=asset_value,
        tool_name="solve_for_target_dti",
    )
    scenario.update(
        {
            "feasible": scenario["calc"]["dti"] <= target + 1e-9,
            "target_dti": target,
            "constraint": "keep_down_payment" if keep_down_payment else "keep_asset_value",
        }
    )
    return scenario


@tool(
    description=(
        "Resolve o prazo necessário para atingir um comprometimento de renda (DTI) alvo, "
        "sem alterar entrada, valor financiado ou valor do bem. Aceita 30 ou 0,30 para "
        "representar 30%. Se o alvo não puder ser atingido antes do prazo máximo permitido "
        "pela idade, devolve o melhor cenário possível com `feasible=false`; nunca invente "
        "um prazo. Use quando Carlos disser para mexer somente no prazo."
    )
)
def solve_term_for_target_dti(
    runtime: ToolRuntime[NegotiationCase],
    dti_target: float,
) -> dict:
    case = runtime.context
    application = case.application
    profile = case.profile
    credit = profile.get("credit") or {}
    income = profile.get("income") or {}
    policy = POLICIES[application["product"]]
    target = _normalize_ratio(dti_target)
    current_age = age_at_maturity(profile.get("birth_date"), 0, date.today())
    age_max_term = (
        max_term_by_age(policy.age_at_maturity_limit.value, current_age)
        if current_age is not None
        else 600
    )

    bounds = term_bounds(
        product=application["product"],
        asset_value=float(application["asset_value"]),
        financed=float(application["requested_amount"]),
        net_income=income.get("net_monthly") or 1.0,
        existing_debt=credit.get("existing_monthly_debt", 0.0),
        score=credit.get("internal_score", 650),
        dti_limit=target,
        ltv_limit=1.0,
        amount_limit=float(application["asset_value"]),
        age_limit=policy.age_at_maturity_limit.value,
        current_age_years=current_age,
        max_search_term=max(1, age_max_term),
    )
    if bounds["feasible"]:
        term = bounds["min_term"]
    else:
        term = bounds.get("max_term") or age_max_term
        term = max(1, term)

    scenario = _simulate(
        case,
        application,
        profile,
        financed=float(application["requested_amount"]),
        term=term,
        rate=None,
        tool_name="solve_term_for_target_dti",
    )
    scenario.update(
        {
            "feasible": bool(bounds["feasible"]),
            "target_dti": target,
            "constraint": "keep_amount_and_down_payment",
            "infeasible_reason": bounds["reason"],
        }
    )
    return scenario


def _normalize_ratio(value: float) -> float:
    ratio = float(value)
    if 1 < ratio <= 100:
        ratio /= 100
    if ratio <= 0 or ratio > 1:
        raise ValueError("dti_target deve estar entre 0 e 1, ou entre 1 e 100 como percentual")
    return ratio


def _simulate(
    case: NegotiationCase,
    application: dict,
    profile: dict,
    *,
    financed: float,
    term: int,
    rate: float | None,
    asset_value: float | None = None,
    tool_name: str,
) -> dict:
    """Shared by both scenario tools: evaluate one credit structure, shape it
    for the model, and log it — so a guessed scenario and a solved one are
    indistinguishable downstream (state, audit log, trace).
    """
    credit = profile.get("credit") or {}
    income = profile.get("income") or {}
    asset_value = float(asset_value if asset_value is not None else application["asset_value"])
    entrada = asset_value - financed

    calc = compute_scenario(
        product=application["product"],
        asset_value=asset_value,
        financed=financed,
        term_months=term,
        net_income=income.get("net_monthly") or 1.0,
        existing_debt=credit.get("existing_monthly_debt", 0.0),
        score=credit.get("internal_score", 650),
        rate=rate,
    )

    # The same decision matrix the customer path ran, on the modified
    # application. So the eligibility the agent reports is the eligibility the
    # bank's rules produce — with the `POL-xxx` ids `tests/test_policy_
    # consistency.py` pins to the corpus on screen.
    decision = evaluate(
        {
            **application,
            "asset_value": asset_value,
            "down_payment": entrada,
            "requested_amount": financed,
            "term_months": term,
        },
        calc,
        profile,
    )

    scenario = {
        "inputs": {
            "asset_value": asset_value,
            "amount": financed,
            "down_payment": entrada,
            "term_months": term,
            "annual_rate": calc["annual_rate"],
        },
        "calc": calc,
        # `calc` keeps full precision for the state and the audit log; `resumo`
        # is what the model quotes. Without it the agent faithfully reports
        # "comprometimento de 28,89345588777942%" — correct, and unusable on a
        # projector. Formatting is not a prompt instruction the model might
        # follow; it is a string it can only copy.
        "resumo": {
            "entrada": brl(entrada),
            "valor_financiado": brl(financed),
            "prazo_meses": term,
            "parcela": brl(calc["monthly_payment"]),
            "ltv": percent(calc["ltv"]),
            "comprometimento_renda": percent(calc["dti"]),
            "taxa_anual": percent(calc["annual_rate"]),
            "cet_anual": percent(calc["cet_annual"]),
            "juros_totais": brl(calc["total_interest"]),
        },
        "outcome": decision["outcome"],
        "policy_refs": decision["policy_refs"],
        "reasons": decision["reasons"],
    }
    case.simulated.append(scenario)
    case.step(
        tool_name,
        down_payment=entrada,
        term_months=term,
        ltv=calc["ltv"],
        dti=calc["dti"],
        monthly_payment=calc["monthly_payment"],
        outcome=decision["outcome"],
    )
    return scenario


@tool(
    description=(
        "Verifica o consentimento de Open Finance e, somente quando ele já foi concedido, "
        "consulta os ativos compartilhados pela cliente. Use quando o caso não fechar pelos "
        "números e um mitigante de risco puder sustentar a decisão."
    )
)
def check_open_finance_assets(runtime: ToolRuntime[NegotiationCase]) -> dict:
    """Report consent and, only when granted, the customer's shared assets. Read-only.

    Takes no arguments: there is exactly one customer in a negotiation and they
    arrive in runtime context, so the model has no opportunity to name someone
    else's account.

    It reports consent, it does not grant it. Consent is the customer's to
    give, and an agent that silently flipped `consent_granted` on a customer's
    behalf is the first thing a bank's risk team would ask about. What this
    unlocks is an *argument* — assets and liquidity a human can weigh — which
    is also the point of the demo beat (SDD 02 §2): the case turns on a
    business reason rather than on a number moving.
    """
    case = runtime.context
    open_finance = case.profile.get("open_finance") or {}
    assets = open_finance.get("shareable_assets") or []

    consent_granted = bool(open_finance.get("consent_granted", False))
    # Without explicit consent, neither the model nor the live trace receives
    # balances or even an asset count. The profile may contain synthetic
    # fixtures, but their presence is not authorization to disclose them.
    visible_assets = assets if consent_granted else []
    total = sum(float(a.get("balance", 0.0)) for a in visible_assets)
    liquid = sum(
        float(a.get("balance", 0.0))
        for a in visible_assets
        if a.get("liquidity") in ("d_plus_0", "d_plus_1")
    )

    result = {
        "consent_granted": consent_granted,
        "shareable_assets": visible_assets,
        "total_balance": total,
        "liquid_balance": liquid,
    }
    detail = {"consent_granted": consent_granted}
    if consent_granted:
        detail.update(asset_count=len(visible_assets), liquid_balance=liquid)
    case.step("check_open_finance_assets", **detail)
    return result
