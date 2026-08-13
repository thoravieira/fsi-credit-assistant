"""SDD 05 §1 — analyst_brief node. Pure unit tests: no `application_id` in
the fixtures, so the `decisions_log` audit write inside the node never fires
and these never touch Atlas.
"""

from langchain_core.messages import AIMessage

from app.graph.nodes.analyst_brief import analyst_brief


class _CapturingLLM:
    """Records the prompt it was invoked with, instead of calling a real model."""

    def __init__(self, response_text: str = "Recomendação: aprovar com condições."):
        self.last_messages = None
        self._response_text = response_text

    def invoke(self, messages):
        self.last_messages = messages
        return AIMessage(self._response_text)


def _state(*, status: str | None) -> dict:
    return {
        "application": {"product": "mortgage", "status": status},
        "calc": {"ltv": 0.75},
        "decision": {"outcome": "manual_review", "policy_refs": ["POL-020"]},
        "precedents": [],
    }


def test_flags_an_already_decided_case_in_the_dossier_context():
    """A case reopened from Aprovados/Reprovações (or, for the seed data, one
    the graph is only touching for the first time already resolved) must not
    read as if the recommendation were still pending — see item 10.
    """
    llm = _CapturingLLM()

    analyst_brief(_state(status="denied"), llm=llm)

    context = llm.last_messages[1].content
    assert "JÁ FOI DECIDIDO" in context
    assert "denied" in context


def test_says_nothing_extra_for_a_still_open_case():
    llm = _CapturingLLM()

    analyst_brief(_state(status="manual_review"), llm=llm)

    assert "JÁ FOI DECIDIDO" not in llm.last_messages[1].content
