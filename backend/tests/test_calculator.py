"""SDD 10 §2 — calculator.py acceptance criteria."""

import pytest

from app.domain.calculator import (
    annual_rate,
    cet_annual,
    dti,
    effective_monthly_rate,
    ltv,
    max_term_by_age,
    pmt,
    schedule_preview,
)


def test_pmt_known_reference_value():
    # PV 448 000, 0.95% monthly, 360 months — pinned against an independent
    # calculator (Tabela Price): PV * i / (1 - (1+i)**-n).
    result = pmt(pv=448_000, monthly_rate=0.0095, n=360)
    assert result == pytest.approx(4402.3553889607, rel=1e-9)


def test_monthly_rate_conversion_is_effective_not_nominal():
    annual = 0.12
    nominal_monthly = annual / 12
    effective = effective_monthly_rate(annual)

    assert effective != pytest.approx(nominal_monthly)
    assert effective == pytest.approx((1 + annual) ** (1 / 12) - 1, rel=1e-12)


def test_ltv():
    assert ltv(financed=448_000, asset_value=560_000) == pytest.approx(0.8)


def test_dti_includes_existing_monthly_debt():
    without_debt = dti(monthly_payment=3000, net_income=10_000, existing_debt=0)
    with_debt = dti(monthly_payment=3000, net_income=10_000, existing_debt=1350)

    assert without_debt == pytest.approx(0.30)
    assert with_debt == pytest.approx((3000 + 1350) / 10_000)
    assert with_debt > without_debt


def test_cet_annual_exceeds_annual_rate_when_fees_present():
    principal = 448_000
    rate = annual_rate("mortgage", ltv_value=0.70, score=780)
    monthly_rate = effective_monthly_rate(rate)
    payment = pmt(pv=principal, monthly_rate=monthly_rate, n=360)

    cet = cet_annual(
        principal=principal,
        monthly_payment=payment,
        n=360,
        monthly_insurance=120.0,
        appraisal_fee=2500.0,
        iof=3800.0,
    )

    assert cet > rate


def test_cet_annual_equals_annual_rate_with_zero_fees():
    principal = 448_000
    rate = 0.106
    monthly_rate = effective_monthly_rate(rate)
    payment = pmt(pv=principal, monthly_rate=monthly_rate, n=360)

    cet = cet_annual(principal=principal, monthly_payment=payment, n=360)

    assert cet == pytest.approx(rate, abs=1e-5)


@pytest.mark.parametrize(
    "ltv_value,score,expected",
    [
        (0.55, 780, 0.098),
        (0.70, 700, 0.098 + 0.015),
        (0.70, 780, 0.098 + 0.008),
        (0.85, 780, 0.098 + 0.025),
    ],
)
def test_annual_rate_mortgage_matches_pol_018(ltv_value, score, expected):
    assert annual_rate("mortgage", ltv_value=ltv_value, score=score) == pytest.approx(expected)


@pytest.mark.parametrize(
    "ltv_value,score,expected",
    [
        (0.65, 720, 0.145),
        (0.80, 650, 0.145 + 0.025),
        (0.80, 720, 0.145 + 0.012),
        (0.95, 720, 0.145 + 0.025),
    ],
)
def test_annual_rate_auto_matches_pol_019(ltv_value, score, expected):
    assert annual_rate("auto", ltv_value=ltv_value, score=score) == pytest.approx(expected)


def test_max_term_by_age_is_pure_months_remaining_to_the_ceiling():
    assert max_term_by_age(age_limit=80, current_age_years=44) == 432  # (80-44)*12


def test_schedule_preview_returns_first_two_and_last_row():
    rows = schedule_preview(pv=448_000, monthly_rate=0.0095, n=360)

    assert len(rows) == 3
    assert [r["installment"] for r in rows] == [1, 2, 360]
    assert rows[-1]["balance"] == pytest.approx(0.0, abs=1.0)
