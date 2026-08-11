"""Brazilian number formatting for text that is read on screen.

Comma decimal separator, dot thousands separator. Lives in `domain/` because
`rules.py` renders thresholds with it and `tests/test_policy_consistency.py`
asserts that the rendering matches the wording of the cited policy document.
"""


def percent(value: float) -> str:
    """`0.70 -> "70%"`, `0.7512 -> "75,1%"`. Round limits drop the decimal so a
    threshold renders exactly as the policy corpus writes it (SDD 10 §4).
    """
    scaled = value * 100
    if round(scaled, 1).is_integer():
        return f"{round(scaled)}%"
    return f"{scaled:.1f}".replace(".", ",") + "%"


def brl(value: float) -> str:
    integer, _, cents = f"{value:.2f}".partition(".")
    grouped = f"{int(integer):,}".replace(",", ".")
    return f"R$ {grouped},{cents}"


def years(value: float) -> str:
    text = f"{value:g}" if float(value).is_integer() else f"{value:.1f}".replace(".", ",")
    return f"{text} anos"
