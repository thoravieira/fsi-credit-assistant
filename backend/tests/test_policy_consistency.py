"""SDD 10 §4 — `rules.py` and the `credit_policies` corpus encode the same
thresholds.

The failure this prevents: the agent cites POL-014 for a rule the code does not
implement. A panel member who reads the cited policy on screen and finds it says
75% while the system applied 80% will discount everything else you showed.

Checked per citation and per product, not "appears somewhere in the corpus" —
`700` appears in POL-009, so a mortgage score floor of 700 would pass the weak
version of this test while every mortgage score policy on screen says 750 or
650. `test_the_invariant_has_teeth` pins that down.

Reads the markdown in `data/policies/` rather than the seeded collection, so the
invariant holds on a clean checkout and does not depend on seed state.
"""

import re
from pathlib import Path

import pytest

from app.domain.rules import POLICIES, Threshold, product_thresholds, render_threshold

POLICIES_DIR = Path(__file__).resolve().parents[2] / "data" / "policies"

ALL_THRESHOLDS = [
    (product, threshold)
    for product, policy in sorted(POLICIES.items())
    for threshold in product_thresholds(policy)
]


def _read_policy(policy_id: str) -> tuple[dict[str, str], str]:
    """Split a policy file into its YAML front matter and its body text."""
    path = POLICIES_DIR / f"{policy_id}.md"
    assert path.exists(), f"{policy_id} is cited by rules.py but not present in {POLICIES_DIR}"

    _, _, rest = path.read_text(encoding="utf-8").partition("---\n")
    front_matter, _, body = rest.partition("---\n")

    fields = {}
    for line in front_matter.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip().strip('"')
    return fields, body


def _appears(rendered: str, body: str) -> bool:
    """Substring match with digit boundaries, so `80%` does not match `180%`."""
    return re.search(rf"(?<!\d){re.escape(rendered)}(?!\d)", body) is not None


def _test_id(case) -> str:
    product, threshold = case
    return f"{product}-{threshold.rule_id}-{threshold.policy_ref}"


@pytest.mark.parametrize("case", ALL_THRESHOLDS, ids=_test_id)
def test_threshold_value_appears_in_the_policy_it_cites(case):
    product, threshold = case
    front_matter, body = _read_policy(threshold.policy_ref)

    rendered = render_threshold(threshold)
    if not rendered:  # `income_verification` carries a citation, not a number
        pytest.skip(f"{threshold.rule_id} is a flag, not a numeric threshold")

    assert _appears(rendered, body), (
        f"rules.py applies {rendered} for {product}.{threshold.rule_id} and cites "
        f"{threshold.policy_ref} ({front_matter.get('title')}), but that policy's text "
        f"never states {rendered}"
    )


@pytest.mark.parametrize("case", ALL_THRESHOLDS, ids=_test_id)
def test_cited_policy_is_about_the_right_product(case):
    product, threshold = case
    front_matter, _ = _read_policy(threshold.policy_ref)

    assert front_matter.get("product") == product, (
        f"{product}.{threshold.rule_id} cites {threshold.policy_ref}, which is a "
        f"{front_matter.get('product')!r} policy"
    )


@pytest.mark.parametrize("product", sorted(POLICIES))
def test_income_verification_cites_an_income_policy(product):
    threshold = POLICIES[product].income_verification
    front_matter, _ = _read_policy(threshold.policy_ref)
    assert front_matter.get("policy_type", "").startswith("income_verification")


def test_the_invariant_has_teeth():
    """A negative control. SDD 10 §3 originally specified a score floor of 700
    for both products; for `mortgage` that number appears in no score policy.
    If this ever passes, the assertion above has stopped checking anything.
    """
    _, pol_008 = _read_policy("POL-008")
    assert not _appears("700", pol_008)

    _, pol_009 = _read_policy("POL-009")
    assert _appears("700", pol_009)  # ...but it is correct for `auto`


def test_every_policy_cited_by_rules_exists():
    cited = {threshold.policy_ref for _product, threshold in ALL_THRESHOLDS}
    on_disk = {path.stem for path in POLICIES_DIR.glob("POL-*.md")}
    assert cited <= on_disk


def test_thresholds_are_covered_exhaustively():
    """Guards the parametrisation itself: if a threshold is added to
    `ProductPolicy` and this list is not regenerated, the new threshold would
    silently go unchecked.
    """
    for product, policy in POLICIES.items():
        checked = {t.rule_id for p, t in ALL_THRESHOLDS if p == product}
        assert checked == {t.rule_id for t in product_thresholds(policy)}
        assert all(isinstance(t, Threshold) for t in product_thresholds(policy))
