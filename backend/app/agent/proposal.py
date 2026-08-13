"""SDD 06 §4-5 — turning a negotiation turn into something a human can approve.

Pure functions: no LLM call, no I/O, no framework import. That is the point.
`pending_approval` is what `await_approval` hands to the human, so it must say
exactly what the system will record — and the cheapest way to guarantee that is
to assemble it from data the system already holds rather than from a second
model call that could paraphrase the recommendation into something subtly
different.

The analyst's verdict is detected by keyword rather than by classifier. That is
a real trade-off and worth stating out loud: it costs nothing in latency (SDD 06
§6 leaves no room for an extra round trip), it cannot hallucinate, and it fails
in the safe direction — an unrecognised phrase simply continues the
negotiation, it never records a decision. What it cannot do is read intent from
an unusual sentence. Since nothing is written until a human confirms at
`/api/approve`, the cost of a miss is one more message.
"""

import re
import unicodedata

_POLICY_ID = re.compile(r"\bPOL-\d{3}\b")

# Order matters and is load-bearing: "não aprovar" contains "aprovar", and
# "aprovar com condições" contains "aprovar". Most specific first.
_VERDICTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "denied",
        ("nao aprovar", "nao aprovo", "negar", "nego", "negado", "negada", "recusar",
         "recuso", "reprovar", "reprovo", "indeferir"),
    ),
    (
        "approved_with_conditions",
        ("aprovar com condicoes", "aprovo com condicoes", "aprovado com condicoes",
         "aprova com condicoes", "com condicoes", "com ressalvas"),
    ),
    ("approved", ("aprovar", "aprovo", "aprovado", "aprovada", "pode aprovar")),
)

# Word-boundary, not raw substring: "aprovados" (plural, e.g. "casos ...
# aprovados") must not trip the "aprovado" keyword. `\b` on both ends of a
# multi-word phrase like "com ressalvas" still works, since the internal
# space is itself a non-word character.
_VERDICT_PATTERNS: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = tuple(
    (outcome, tuple(re.compile(rf"\b{re.escape(keyword)}\b") for keyword in keywords))
    for outcome, keywords in _VERDICTS
)


def _fold(text: str) -> str:
    """Lowercase and strip accents, so "condições" and "condicoes" both match."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def detect_verdict(analyst_message: str) -> str | None:
    """The analyst's final call, or `None` while the negotiation continues."""
    folded = _fold(analyst_message)
    for outcome, patterns in _VERDICT_PATTERNS:
        if any(pattern.search(folded) for pattern in patterns):
            return outcome
    return None


def cited_policies(text: str) -> list[str]:
    """The `POL-xxx` ids the agent cited, in order, without duplicates."""
    seen: list[str] = []
    for match in _POLICY_ID.findall(text):
        if match not in seen:
            seen.append(match)
    return seen


def build_proposal(
    *,
    analyst_message: str,
    agent_message: str,
    application: dict,
    scenario: dict | None,
    precedents: list[dict],
) -> dict | None:
    """The payload `await_approval` shows the human, or `None` if they have not
    called for a decision yet.

    `scenario` is the structure the recommendation is about — a real
    `recalculate_scenario` result, never a restatement — and `policy_refs` are
    read back out of the agent's own prose, so the approval screen cites what
    the analyst actually read.
    """
    outcome = detect_verdict(analyst_message)
    if outcome is None:
        return None

    return {
        "outcome": outcome,
        "application_id": application.get("application_id"),
        "scenario": scenario,
        "rationale": agent_message,
        "policy_refs": cited_policies(agent_message),
        "precedent_refs": [p["_id"] for p in precedents if p.get("_id")],
    }
