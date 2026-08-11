"""SDD 10 §3 — decision matrix, tested at every boundary.

Every rule is `<=` or `>=`, so the exact threshold is *inside* the limit. Each
test therefore checks three points: just inside, exactly on, and just outside.

`evaluate` takes `today=` so age boundaries are deterministic — the alternative
is a test that changes its answer on a birthday.
"""

from dataclasses import fields
from datetime import date, timedelta

import pytest

from app.domain.rules import (
    POLICIES,
    Threshold,
    _age_at_maturity,
    evaluate,
    product_thresholds,
)

TODAY = date(2026, 8, 11)


def _case(
    product,
    *,
    ltv,
    dti,
    amount,
    score=None,
    term_months=360,
    verified=True,
    birth_date="1990-04-17",
):
    application = {"product": product, "requested_amount": amount, "term_months": term_months}
    calc = {"ltv": ltv, "dti": dti}
    profile = {
        "birth_date": birth_date,
        "credit": {} if score is None else {"internal_score": score},
        "income": {"verified": verified, "net_monthly": 11_200.0},
    }
    return application, calc, profile


def _outcome(product, **kwargs) -> str:
    return evaluate(*_case(product, **kwargs), today=TODAY)["outcome"]


# Comfortably inside every auto-approval limit for each product.
APPROVABLE = {
    "mortgage": {"ltv": 0.55, "dti": 0.25, "amount": 200_000.0, "score": 782},
    "auto": {"ltv": 0.60, "dti": 0.25, "amount": 50_000.0, "score": 760, "term_months": 60},
}


def _approvable(product, **overrides):
    kwargs = dict(APPROVABLE[product])
    kwargs.update(overrides)
    return _outcome(product, **kwargs)


def test_baseline_cases_auto_approve():
    for product in POLICIES:
        assert _approvable(product) == "auto_approved"


# --- rule_id integrity -----------------------------------------------------


@pytest.mark.parametrize("product", sorted(POLICIES))
def test_rule_ids_match_their_field_names(product):
    """`ProductPolicy` field name is the rule id. If they drift, `breached_rules`
    starts naming a rule that does not exist in the SDD 10 §3 table.
    """
    policy = POLICIES[product]
    for field in fields(policy):
        assert getattr(policy, field.name).rule_id == field.name


@pytest.mark.parametrize("product", sorted(POLICIES))
def test_every_threshold_cites_a_policy(product):
    for threshold in product_thresholds(POLICIES[product]):
        assert threshold.policy_ref.startswith("POL-")


# --- auto-approval boundaries: inside -> auto_approved, outside -> manual ---


@pytest.mark.parametrize(
    "product,field,delta,expected",
    [
        (product, field, delta, expected)
        for product in ("mortgage", "auto")
        for field, delta, expected in (
            ("ltv", -0.01, "auto_approved"),
            ("ltv", 0.0, "auto_approved"),
            ("dti", -0.01, "auto_approved"),
            ("dti", 0.0, "auto_approved"),
            ("dti", +0.01, "manual_review"),
        )
    ],
)
def test_ratio_auto_approval_boundaries(product, field, delta, expected):
    limit = getattr(POLICIES[product], f"{field}_auto_approval_limit").value
    assert _approvable(product, **{field: limit + delta}) == expected


def test_ltv_just_over_the_auto_approval_limit():
    """Split from the ratio sweep because the two products diverge here.

    For `mortgage` the auto-approval limit (0.70, POL-020) sits below the
    absolute limit (0.80, POL-001), so 0.71 routes to a human. For `auto` the
    two coincide at 0.80 — POL-021's approval band and POL-003's hard ceiling
    are the same number — so 0.81 is denied outright and LTV can never *only*
    trigger manual review. That follows from using POL-003's conservative 0.80
    for every vehicle (SDD 10 §3, "deliberately not implemented").
    """
    assert _approvable("mortgage", ltv=0.71) == "manual_review"
    assert _approvable("auto", ltv=0.81) == "denied"


@pytest.mark.parametrize("product", sorted(POLICIES))
def test_score_auto_approval_floor_boundary(product):
    floor = int(POLICIES[product].score_auto_approval_floor.value)
    assert _approvable(product, score=floor + 1) == "auto_approved"
    assert _approvable(product, score=floor) == "auto_approved"
    assert _approvable(product, score=floor - 1) == "manual_review"


@pytest.mark.parametrize("product", sorted(POLICIES))
def test_amount_auto_approval_limit_boundary(product):
    limit = POLICIES[product].amount_auto_approval_limit.value
    assert _approvable(product, amount=limit - 0.01) == "auto_approved"
    assert _approvable(product, amount=limit) == "auto_approved"
    assert _approvable(product, amount=limit + 0.01) == "manual_review"


@pytest.mark.parametrize("product", sorted(POLICIES))
def test_unverified_income_blocks_auto_approval_but_does_not_deny(product):
    assert _approvable(product, verified=False) == "manual_review"
    assert _approvable(product, verified=None) == "manual_review"


# --- absolute boundaries: outside -> denied --------------------------------


@pytest.mark.parametrize("product,field", [(p, f) for p in POLICIES for f in ("ltv", "dti")])
def test_ratio_absolute_boundaries(product, field):
    limit = getattr(POLICIES[product], f"{field}_absolute_limit").value
    assert _approvable(product, **{field: limit}) != "denied"
    assert _approvable(product, **{field: limit + 0.01}) == "denied"


@pytest.mark.parametrize("product", sorted(POLICIES))
def test_score_absolute_floor_boundary(product):
    floor = int(POLICIES[product].score_absolute_floor.value)
    assert _approvable(product, score=floor) != "denied"
    assert _approvable(product, score=floor - 1) == "denied"


def _birth_date_for_age_at_maturity(target_years: float, term_months: int) -> date:
    """A birth date whose `age_at_maturity` lands at or just below `target_years`.

    Birth dates are whole days, so the reachable ages are quantised to about
    1/365.25 ≈ 0.0027 years. Truncating rather than rounding guarantees the
    result never overshoots — `round()` puts the "exactly 80" case at 80.0007
    and the test would assert the opposite of what it means to.
    """
    current_age_years = target_years - term_months / 12
    return TODAY - timedelta(days=int(current_age_years * 365.25))


@pytest.mark.parametrize("product", sorted(POLICIES))
def test_age_at_maturity_boundary(product):
    """`age_at_maturity = current_age_years + term_months / 12` (SDD 10 §3)."""
    limit = POLICIES[product].age_at_maturity_limit.value
    term_months = APPROVABLE[product].get("term_months", 360)

    for target, expected in ((limit - 0.05, "auto_approved"), (limit, "auto_approved")):
        birth_date = _birth_date_for_age_at_maturity(target, term_months)
        # Prove the fixture is on the side of the limit the assertion assumes.
        assert _age_at_maturity(birth_date, term_months, TODAY) <= limit
        assert _approvable(product, birth_date=birth_date.isoformat()) == expected

    over = _birth_date_for_age_at_maturity(limit + 0.05, term_months)
    assert _age_at_maturity(over, term_months, TODAY) > limit
    assert _approvable(product, birth_date=over.isoformat()) == "denied"


# --- missing data is not a breach ------------------------------------------


@pytest.mark.parametrize("product", sorted(POLICIES))
def test_missing_score_blocks_auto_approval_without_denying(product):
    """Absence of evidence is not evidence of a breach: a profile with no score
    must not be denied on the absolute floor, only held back from automatic
    approval.
    """
    assert _approvable(product, score=None) == "manual_review"


@pytest.mark.parametrize("product", sorted(POLICIES))
def test_missing_birth_date_blocks_auto_approval_without_denying(product):
    assert _approvable(product, birth_date=None) == "manual_review"
    assert _approvable(product, birth_date="nao-e-uma-data") == "manual_review"


# --- every decision is explainable -----------------------------------------


@pytest.mark.parametrize("product", sorted(POLICIES))
def test_every_outcome_is_cited(product):
    """SDD 10 §3 — non-empty `reasons` and `policy_refs` on every outcome,
    `auto_approved` included. A decision without citations is not explainable.
    """
    policy = POLICIES[product]
    scenarios = {
        "auto_approved": dict(APPROVABLE[product]),
        "manual_review": {**APPROVABLE[product], "dti": policy.dti_auto_approval_limit.value + 0.01},
        "denied": {**APPROVABLE[product], "dti": policy.dti_absolute_limit.value + 0.01},
    }
    for expected, kwargs in scenarios.items():
        result = evaluate(*_case(product, **kwargs), today=TODAY)
        assert result["outcome"] == expected
        assert result["reasons"], expected
        assert result["policy_refs"], expected
        assert all(ref.startswith("POL-") for ref in result["policy_refs"])
        assert len(result["policy_refs"]) == len(set(result["policy_refs"]))


@pytest.mark.parametrize("product", sorted(POLICIES))
def test_breached_rules_are_empty_only_on_auto_approval(product):
    policy = POLICIES[product]

    approved = evaluate(*_case(product, **APPROVABLE[product]), today=TODAY)
    assert approved["breached_rules"] == []

    over_dti = {**APPROVABLE[product], "dti": policy.dti_auto_approval_limit.value + 0.01}
    reviewed = evaluate(*_case(product, **over_dti), today=TODAY)
    assert reviewed["breached_rules"] == ["dti_auto_approval_limit"]

    way_over = {**APPROVABLE[product], "dti": policy.dti_absolute_limit.value + 0.01}
    denied = evaluate(*_case(product, **way_over), today=TODAY)
    assert denied["breached_rules"] == ["dti_absolute_limit"]


def test_multiple_breaches_are_all_reported():
    policy = POLICIES["mortgage"]
    result = evaluate(
        *_case("mortgage", ltv=0.75, dti=0.35, amount=400_000.0, score=700),
        today=TODAY,
    )
    assert result["outcome"] == "manual_review"
    assert set(result["breached_rules"]) == {
        "ltv_auto_approval_limit",
        "dti_auto_approval_limit",
        "score_auto_approval_floor",
        "amount_auto_approval_limit",
    }
    assert len(result["reasons"]) == 4
    assert policy.ltv_auto_approval_limit.policy_ref in result["policy_refs"]


def test_unknown_product_raises():
    with pytest.raises(ValueError, match="no decision policy"):
        evaluate(
            {"product": "consignado", "requested_amount": 1000.0, "term_months": 12},
            {"ltv": 0.1, "dti": 0.1},
            {},
            today=TODAY,
        )


# --- reasons are demo-facing Portuguese ------------------------------------


def test_reasons_use_brazilian_number_formatting():
    """These strings are read on screen by Mariana and Carlos (CLAUDE.md:
    demo-facing content is Portuguese)."""
    result = evaluate(
        *_case("mortgage", ltv=0.7512, dti=0.3579, amount=400_000.0, score=782),
        today=TODAY,
    )
    joined = " ".join(result["reasons"])
    assert "75,1%" in joined
    assert "35,8%" in joined
    assert "R$ 400.000,00" in joined
    assert "R$ 300.000,00" in joined


def test_denial_reason_names_the_absolute_limit():
    result = evaluate(
        *_case("mortgage", ltv=0.55, dti=0.475, amount=200_000.0, score=782), today=TODAY
    )
    assert result["outcome"] == "denied"
    assert result["policy_refs"] == ["POL-004"]
    assert "47,5%" in result["reasons"][0]
    assert "40%" in result["reasons"][0]


# --- architectural invariant -----------------------------------------------


def test_domain_imports_no_llm_framework():
    """SDD 10 acceptance / CLAUDE.md — zero imports from `langchain*` or
    `langgraph*` anywhere in `domain/`.

    This is the rule that makes "the LLM never computes a number" checkable
    rather than aspirational. Asserted on the source rather than on
    `sys.modules`, because by the time this runs the test session has imported
    LangChain a dozen times over.
    """
    import ast
    from pathlib import Path

    domain_dir = Path(__file__).resolve().parents[1] / "app" / "domain"
    offenders = []

    for path in domain_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                # `app.graph.state` is banned too: it re-exports the same
                # TypedDicts but pulls `langchain_core` in behind them.
                if name.startswith(("langchain", "langgraph", "app.graph")):
                    offenders.append(f"{path.name}: {name}")

    assert offenders == []


def test_thresholds_are_frozen():
    """`Threshold` is immutable so a node cannot mutate the policy table at
    runtime — the table is the contract the consistency test certifies.
    """
    with pytest.raises(Exception):
        POLICIES["mortgage"].dti_absolute_limit.value = 0.99  # type: ignore[misc]
    assert isinstance(POLICIES["mortgage"].dti_absolute_limit, Threshold)
