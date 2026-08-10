"""SDD 05 — customer-path nodes (router → customer_response).

Per SDD 14 §2: real DB (seeded Day 1 on Atlas), fake LLM. `decision` is
excluded — it depends on `domain/rules.py`, deferred to the Opus session.
"""

from unittest.mock import patch

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import HumanMessage

from app.graph.nodes.credit_calculator import credit_calculator
from app.graph.nodes.customer_response import customer_response
from app.graph.nodes.intake import _ExtractedFields, intake
from app.graph.nodes.load_context import load_context
from app.graph.nodes.policy_retrieval import policy_retrieval
from app.graph.nodes.router import router


def _base_state(**overrides):
    state = {
        "messages": [],
        "persona": "customer",
        "stage": "intake",
        "application": None,
        "profile": None,
        "memories": [],
        "policies": [],
        "precedents": [],
        "calc": None,
        "decision": None,
        "scenarios": [],
        "pending_approval": None,
    }
    state.update(overrides)
    return state


class _FakeStructuredLLM:
    def __init__(self, result):
        self._result = result

    def with_structured_output(self, schema):
        return self

    def invoke(self, messages):
        return self._result


def test_router_is_a_noop():
    assert router(_base_state()) == {}


def test_intake_merges_and_marks_complete():
    prior = {"customer_id": "CUST-0001", "product": "mortgage"}
    state = _base_state(
        application=prior,
        messages=[HumanMessage("Quero financiar com entrada de 112 mil, prazo de 360 meses")],
    )
    fake_llm = _FakeStructuredLLM(
        _ExtractedFields(asset_value=560_000.0, down_payment=112_000.0, term_months=360)
    )

    result = intake(state, llm=fake_llm)

    app = result["application"]
    assert app["product"] == "mortgage"
    assert app["asset_value"] == 560_000.0
    assert app["requested_amount"] == pytest.approx(448_000.0)
    assert result["stage"] == "assessment"


def test_intake_leaves_stage_unchanged_when_incomplete():
    state = _base_state(application=None, messages=[HumanMessage("quero financiar um apartamento")])
    fake_llm = _FakeStructuredLLM(_ExtractedFields(product="mortgage"))

    result = intake(state, llm=fake_llm)

    assert "stage" not in result
    assert result["application"] == {"product": "mortgage"}


def test_load_context_reads_seeded_profile():
    state = _base_state(application={"customer_id": "CUST-0001"})

    with patch("app.graph.nodes.load_context.get_stream_writer") as get_writer:
        result = load_context(state)

    assert result["profile"]["_id"] == "CUST-0001"
    assert isinstance(result["memories"], list)
    get_writer.return_value.assert_called_once()


def test_policy_retrieval_returns_matched_policies():
    application = {
        "product": "mortgage",
        "asset_value": 560_000.0,
        "down_payment": 112_000.0,
        "requested_amount": 448_000.0,
        "term_months": 360,
    }
    profile = {
        "credit": {"internal_score": 782, "existing_monthly_debt": 1350.0},
        "income": {"net_monthly": 11_200.0},
        "employment": {"type": "clt"},
    }
    state = _base_state(application=application, profile=profile)

    with patch("app.graph.nodes.policy_retrieval.get_stream_writer") as get_writer:
        result = policy_retrieval(state)

    assert len(result["policies"]) > 0
    assert all(p["product"] == "mortgage" for p in result["policies"])
    assert get_writer.return_value.call_count == 2


def test_credit_calculator_is_pure_and_consistent():
    application = {
        "product": "mortgage",
        "asset_value": 560_000.0,
        "requested_amount": 448_000.0,
        "term_months": 360,
    }
    profile = {
        "credit": {"internal_score": 782, "existing_monthly_debt": 1350.0},
        "income": {"net_monthly": 11_200.0},
    }
    state = _base_state(application=application, profile=profile)

    result = credit_calculator(state)
    calc = result["calc"]

    assert calc["ltv"] == pytest.approx(0.8)
    assert calc["cet_annual"] > calc["annual_rate"]
    assert calc["monthly_payment"] > 0
    assert len(calc["schedule_preview"]) == 3


def test_customer_response_asks_for_missing_fields():
    state = _base_state(application={"product": "mortgage"})
    fake_llm = FakeListChatModel(responses=["Poderia me informar o valor de entrada?"])

    result = customer_response(state, llm=fake_llm)

    assert "entrada" in result["messages"][0].content


def test_customer_response_grounds_answer_in_calc_and_policies():
    application = {
        "product": "mortgage",
        "asset_value": 560_000.0,
        "down_payment": 112_000.0,
        "term_months": 360,
    }
    calc = {"monthly_payment": 4402.36, "annual_rate": 0.098}
    decision = {"outcome": "auto_approved", "reasons": ["LTV dentro do limite"], "policy_refs": ["POL-001"]}
    state = _base_state(application=application, calc=calc, decision=decision)
    fake_llm = FakeListChatModel(responses=["Sua parcela ficou em R$ 4.402,36."])

    result = customer_response(state, llm=fake_llm)

    assert "4.402,36" in result["messages"][0].content


def test_decision_node_blocked_on_domain_rules():
    """SDD 10 §3 — `domain/rules.py` is deferred to the Opus session. This
    documents the interface `decision.py` expects:
    `evaluate(application, calc, profile) -> Decision`. Once rules.py lands,
    this import will start succeeding — that's the signal to replace this
    canary with real decision-node tests.
    """
    with pytest.raises(ModuleNotFoundError):
        import app.graph.nodes.decision  # noqa: F401
