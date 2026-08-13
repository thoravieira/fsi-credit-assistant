"""SDD 10 §3 — the credit decision matrix.

Deterministic and fully cited: every threshold carries the `POL-xxx` that
states it, and `tests/test_policy_consistency.py` asserts the number in this
file matches the number in that policy for that product (SDD 10 §4).

Zero LLM involvement, zero LangChain imports. The model chooses the scenario;
this module decides it.
"""

from dataclasses import dataclass, fields
from datetime import date, datetime
from typing import Any, Literal, Mapping, TypedDict

# Brazilian formatting: comma decimal separator, dot thousands separator. These
# strings are read on screen by Mariana and Carlos, and
# `tests/test_policy_consistency.py` asserts that a rendered threshold matches
# the wording of the policy document `rules.py` cites for it.
from app.domain.formatting import brl as _brl, percent as _pct, years as _years

Product = Literal["mortgage", "auto"]
Outcome = Literal["auto_approved", "manual_review", "denied"]

# Read structurally — the authoritative shapes are `CreditApplication`,
# `CalcResult` and the `customer_profiles` document in SDD 02/04 §2.
CreditApplication = Mapping[str, Any]
CalcResult = Mapping[str, Any]
Profile = Mapping[str, Any]


class Decision(TypedDict):
    """Structural mirror of `graph.state.Decision` (SDD 04 §2).

    Duplicated rather than imported: `graph.state` pulls in `langchain_core`,
    and `domain/` must import neither `langchain*` nor `langgraph*`.
    """

    outcome: Outcome
    reasons: list[str]
    policy_refs: list[str]
    breached_rules: list[str]


ThresholdKind = Literal["ratio", "score", "amount", "years", "flag"]


@dataclass(frozen=True)
class Threshold:
    rule_id: str
    value: float | None
    policy_ref: str
    kind: ThresholdKind


@dataclass(frozen=True)
class ProductPolicy:
    """Thresholds for one product. Field name == `rule_id` by convention,
    asserted in `tests/test_rules.py`.
    """

    # Breaching any of these denies outright.
    ltv_absolute_limit: Threshold
    dti_absolute_limit: Threshold
    score_absolute_floor: Threshold
    age_at_maturity_limit: Threshold
    # Breaching any of these sends the case to a human instead.
    ltv_auto_approval_limit: Threshold
    dti_auto_approval_limit: Threshold
    score_auto_approval_floor: Threshold
    amount_auto_approval_limit: Threshold
    income_verification: Threshold

    @property
    def absolute_rules(self) -> tuple[Threshold, ...]:
        return (
            self.ltv_absolute_limit,
            self.dti_absolute_limit,
            self.score_absolute_floor,
            self.age_at_maturity_limit,
        )

    @property
    def auto_approval_rules(self) -> tuple[Threshold, ...]:
        return (
            self.ltv_auto_approval_limit,
            self.dti_auto_approval_limit,
            self.score_auto_approval_floor,
            self.amount_auto_approval_limit,
            self.income_verification,
        )


# SDD 10 §3. `auto` uses POL-003's conservative 0.80 rather than POL-002's 0.90
# for new vehicles because `CreditApplication` carries no vehicle-age field —
# this under-approves rather than over-approves. POL-022/023 (inventário) has no
# input in the state schema at all and is not evaluated here.
POLICIES: dict[Product, ProductPolicy] = {
    "mortgage": ProductPolicy(
        ltv_absolute_limit=Threshold("ltv_absolute_limit", 0.80, "POL-001", "ratio"),
        dti_absolute_limit=Threshold("dti_absolute_limit", 0.40, "POL-004", "ratio"),
        score_absolute_floor=Threshold("score_absolute_floor", 650, "POL-008", "score"),
        age_at_maturity_limit=Threshold("age_at_maturity_limit", 80, "POL-006", "years"),
        ltv_auto_approval_limit=Threshold("ltv_auto_approval_limit", 0.70, "POL-020", "ratio"),
        dti_auto_approval_limit=Threshold("dti_auto_approval_limit", 0.30, "POL-004", "ratio"),
        score_auto_approval_floor=Threshold(
            "score_auto_approval_floor", 750, "POL-008", "score"
        ),
        amount_auto_approval_limit=Threshold(
            "amount_auto_approval_limit", 300_000, "POL-020", "amount"
        ),
        income_verification=Threshold("income_verification", None, "POL-012", "flag"),
    ),
    "auto": ProductPolicy(
        ltv_absolute_limit=Threshold("ltv_absolute_limit", 0.80, "POL-003", "ratio"),
        dti_absolute_limit=Threshold("dti_absolute_limit", 0.45, "POL-005", "ratio"),
        score_absolute_floor=Threshold("score_absolute_floor", 600, "POL-009", "score"),
        age_at_maturity_limit=Threshold("age_at_maturity_limit", 80, "POL-007", "years"),
        ltv_auto_approval_limit=Threshold("ltv_auto_approval_limit", 0.80, "POL-021", "ratio"),
        dti_auto_approval_limit=Threshold("dti_auto_approval_limit", 0.35, "POL-005", "ratio"),
        score_auto_approval_floor=Threshold(
            "score_auto_approval_floor", 700, "POL-009", "score"
        ),
        amount_auto_approval_limit=Threshold(
            "amount_auto_approval_limit", 80_000, "POL-021", "amount"
        ),
        income_verification=Threshold("income_verification", None, "POL-013", "flag"),
    ),
}


def product_thresholds(policy: ProductPolicy) -> tuple[Threshold, ...]:
    """Every threshold on a `ProductPolicy`, in declaration order."""
    return tuple(getattr(policy, field.name) for field in fields(policy))


def render_threshold(threshold: Threshold) -> str:
    """The threshold as it should read in a policy document — the string
    `tests/test_policy_consistency.py` looks for in the cited `POL-xxx`.
    """
    if threshold.value is None:
        return ""
    if threshold.kind == "ratio":
        return _pct(threshold.value)
    if threshold.kind == "amount":
        return _brl(threshold.value)
    if threshold.kind == "years":
        return _years(threshold.value)
    return f"{int(threshold.value)}"


# --- Fact extraction -------------------------------------------------------


def age_at_maturity(birth_date: Any, term_months: int, today: date) -> float | None:
    """`current_age_years + term_months / 12` (SDD 10 §3). Returns `None` when
    the profile carries no usable birth date — the caller treats that as
    "cannot confirm", never as "passes".
    """
    if birth_date is None:
        return None
    if isinstance(birth_date, datetime):
        born = birth_date.date()
    elif isinstance(birth_date, date):
        born = birth_date
    else:
        try:
            born = date.fromisoformat(str(birth_date)[:10])
        except ValueError:
            return None
    return (today - born).days / 365.25 + term_months / 12


def evaluate(
    application: CreditApplication,
    calc: CalcResult,
    profile: Profile,
    *,
    today: date | None = None,
) -> Decision:
    """Apply the SDD 10 §3 matrix. `today` is injectable so age boundaries are
    testable without freezing the clock.
    """
    product = application.get("product")
    policy = POLICIES.get(product)
    if policy is None:
        raise ValueError(f"no decision policy for product {product!r}")

    today = today or date.today()
    profile = profile or {}
    credit = profile.get("credit") or {}
    income = profile.get("income") or {}

    ltv = float(calc["ltv"])
    dti = float(calc["dti"])
    amount = float(application["requested_amount"])
    score = credit.get("internal_score")
    income_verified = income.get("verified")
    age = age_at_maturity(profile.get("birth_date"), int(application["term_months"]), today)

    breaches: list[tuple[Threshold, str]] = []

    # Absolute limits — a breach here denies outright. A missing score or birth
    # date is absence of evidence, not evidence of a breach, so it never denies;
    # it blocks auto-approval below instead.
    if ltv > policy.ltv_absolute_limit.value:
        breaches.append(
            (
                policy.ltv_absolute_limit,
                f"LTV de {_pct(ltv)} acima do limite máximo de "
                f"{_pct(policy.ltv_absolute_limit.value)} admitido para o produto.",
            )
        )
    if dti > policy.dti_absolute_limit.value:
        breaches.append(
            (
                policy.dti_absolute_limit,
                f"Comprometimento de renda de {_pct(dti)} acima do limite máximo de "
                f"{_pct(policy.dti_absolute_limit.value)}, com reprovação automática.",
            )
        )
    if score is not None and score < policy.score_absolute_floor.value:
        breaches.append(
            (
                policy.score_absolute_floor,
                f"Score interno de {int(score)} abaixo do mínimo de "
                f"{int(policy.score_absolute_floor.value)} exigido para o produto.",
            )
        )
    if age is not None and age > policy.age_at_maturity_limit.value:
        breaches.append(
            (
                policy.age_at_maturity_limit,
                f"Idade somada ao prazo atinge {_years(age)} ao final do contrato, "
                f"acima do limite de {_years(policy.age_at_maturity_limit.value)}.",
            )
        )

    if breaches:
        return _decision("denied", breaches)

    # Auto-approval criteria — a breach here routes to a human.
    if ltv > policy.ltv_auto_approval_limit.value:
        breaches.append(
            (
                policy.ltv_auto_approval_limit,
                f"LTV de {_pct(ltv)} acima de {_pct(policy.ltv_auto_approval_limit.value)}, "
                "limite da aprovação automática.",
            )
        )
    if dti > policy.dti_auto_approval_limit.value:
        breaches.append(
            (
                policy.dti_auto_approval_limit,
                f"Comprometimento de renda de {_pct(dti)} acima de "
                f"{_pct(policy.dti_auto_approval_limit.value)}, limite da aprovação automática.",
            )
        )
    if score is None:
        breaches.append(
            (
                policy.score_auto_approval_floor,
                "Score interno não disponível no cadastro; a faixa de score não pôde ser "
                "confirmada automaticamente.",
            )
        )
    elif score < policy.score_auto_approval_floor.value:
        breaches.append(
            (
                policy.score_auto_approval_floor,
                f"Score interno de {int(score)} abaixo de "
                f"{int(policy.score_auto_approval_floor.value)}, faixa da aprovação automática.",
            )
        )
    if amount > policy.amount_auto_approval_limit.value:
        breaches.append(
            (
                policy.amount_auto_approval_limit,
                f"Valor solicitado de {_brl(amount)} acima da alçada de "
                f"{_brl(policy.amount_auto_approval_limit.value)} para aprovação automática.",
            )
        )
    if income_verified is not True:
        breaches.append(
            (
                policy.income_verification,
                "Renda não consta como comprovada no cadastro; a comprovação é condição da "
                "aprovação automática.",
            )
        )
    if age is None:
        breaches.append(
            (
                policy.age_at_maturity_limit,
                "Data de nascimento não disponível no cadastro; o limite de idade somada ao "
                "prazo não pôde ser verificado automaticamente.",
            )
        )

    if breaches:
        return _decision("manual_review", breaches)

    # Nothing breached: cite the limits the application stayed within, so an
    # approval is as explainable as a refusal (SDD 10 §3).
    satisfied: list[tuple[Threshold, str]] = [
        (
            policy.ltv_auto_approval_limit,
            f"LTV de {_pct(ltv)} dentro do limite de "
            f"{_pct(policy.ltv_auto_approval_limit.value)}.",
        ),
        (
            policy.dti_auto_approval_limit,
            f"Comprometimento de renda de {_pct(dti)} dentro do limite de "
            f"{_pct(policy.dti_auto_approval_limit.value)}.",
        ),
        (
            policy.score_auto_approval_floor,
            f"Score interno de {int(score)}, igual ou superior ao mínimo de "
            f"{int(policy.score_auto_approval_floor.value)}.",
        ),
        (
            policy.amount_auto_approval_limit,
            f"Valor solicitado de {_brl(amount)} dentro da alçada de aprovação automática "
            f"de {_brl(policy.amount_auto_approval_limit.value)}.",
        ),
        (
            policy.income_verification,
            "Renda comprovada e verificada no cadastro.",
        ),
        (
            policy.age_at_maturity_limit,
            f"Idade somada ao prazo atinge {_years(age)} ao final do contrato, dentro do "
            f"limite de {_years(policy.age_at_maturity_limit.value)}.",
        ),
    ]
    return _decision("auto_approved", satisfied, breached=False)


def _decision(
    outcome: Outcome, cited: list[tuple[Threshold, str]], *, breached: bool = True
) -> Decision:
    refs: list[str] = []
    for threshold, _reason in cited:
        if threshold.policy_ref not in refs:
            refs.append(threshold.policy_ref)
    return {
        "outcome": outcome,
        "reasons": [reason for _threshold, reason in cited],
        "policy_refs": refs,
        "breached_rules": [threshold.rule_id for threshold, _ in cited] if breached else [],
    }
