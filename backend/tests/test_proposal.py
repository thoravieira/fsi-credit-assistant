"""SDD 06 §4-5 — verdict detection and proposal assembly. Pure, no I/O."""

import pytest

from app.agent.proposal import build_proposal, cited_policies, detect_verdict


@pytest.mark.parametrize(
    "message, expected",
    [
        ("pode aprovar", "approved"),
        ("Aprovo essa estrutura.", "approved"),
        ("aprovar com condições", "approved_with_conditions"),
        # Accents are folded, so the analyst can type either spelling.
        ("aprovar com condicoes", "approved_with_conditions"),
        ("aprovado, mas com ressalvas", "approved_with_conditions"),
        ("vamos negar", "denied"),
        ("prefiro não aprovar", "denied"),
        # Still negotiating: nothing is proposed, so nothing can be recorded.
        ("e se a entrada subisse para 168 mil?", None),
        ("qual o LTV nesse caso?", None),
        ("", None),
        # A question that merely *mentions* approved precedents must not read
        # as a verdict: "aprovados" contains "aprovado" as a substring, but
        # is a different word (plural, describing other cases).
        (
            "existem casos semelhantes aprovados com comprometimento da renda "
            "acima de 30%? o que foi sugerido?",
            None,
        ),
    ],
)
def test_detect_verdict(message, expected):
    assert detect_verdict(message) == expected


def test_specific_verdicts_win_over_the_substring_they_contain():
    """"não aprovar" and "aprovar com condições" both contain "aprovar". The
    ordering in `_VERDICTS` is what stops either from reading as a plain
    approval, so it is asserted rather than assumed.
    """
    assert detect_verdict("não aprovar com condições") == "denied"
    assert detect_verdict("aprovar com condições de MIP") == "approved_with_conditions"


def test_cited_policies_are_ordered_and_deduplicated():
    text = "LTV dentro de POL-020, renda comprovada (POL-012), e novamente POL-020."
    assert cited_policies(text) == ["POL-020", "POL-012"]


def test_no_proposal_while_the_negotiation_continues():
    assert (
        build_proposal(
            analyst_message="e se o prazo fosse 420 meses?",
            agent_message="A parcela cairia para R$ 3.900,00 (POL-006).",
            application={"application_id": "APP-1"},
            scenario={"calc": {}},
            precedents=[],
        )
        is None
    )


def test_proposal_carries_the_scenario_and_the_agents_citations():
    proposal = build_proposal(
        analyst_message="aprovar com condições",
        agent_message="Com entrada de 30% o LTV cai para 70% (POL-020) e a renda "
        "está comprovada (POL-012).",
        application={"application_id": "APP-20260814-0001"},
        scenario={"inputs": {"down_payment": 168_000.0}, "calc": {"ltv": 0.70}},
        precedents=[{"_id": "CASE-2025-0417"}, {"score": 0.4}],
    )

    assert proposal["outcome"] == "approved_with_conditions"
    assert proposal["application_id"] == "APP-20260814-0001"
    assert proposal["scenario"]["calc"]["ltv"] == 0.70
    assert proposal["policy_refs"] == ["POL-020", "POL-012"]
    assert proposal["precedent_refs"] == ["CASE-2025-0417"]
