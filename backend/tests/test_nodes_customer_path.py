"""SDD 05 — customer-path nodes (router → customer_response).

Per SDD 14 §2: real DB (seeded Day 1 on Atlas), fake LLM.
"""

from datetime import date
from unittest.mock import patch

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import HumanMessage

from app.db import get_db
from app.domain.calculator import max_financeable, max_term_by_age
from app.domain.rules import POLICIES, age_at_maturity
from app.graph.nodes.credit_calculator import credit_calculator
from app.graph.nodes.customer_response import customer_response
from app.graph.nodes.decision import decision
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
        messages=[HumanMessage("Quero financiar com entrada de 100 mil, prazo de 360 meses")],
    )
    fake_llm = _FakeStructuredLLM(
        _ExtractedFields(
            asset_value=400_000.0,
            down_payment=100_000.0,
            term_months=360,
            purpose="Compra de imóvel residencial",
        )
    )

    result = intake(state, llm=fake_llm)

    app = result["application"]
    assert app["product"] == "mortgage"
    assert app["asset_value"] == 400_000.0
    assert app["requested_amount"] == pytest.approx(300_000.0)
    assert result["stage"] == "assessment"


def test_intake_leaves_stage_unchanged_when_incomplete():
    state = _base_state(application=None, messages=[HumanMessage("quero financiar um apartamento")])
    fake_llm = _FakeStructuredLLM(_ExtractedFields(product="mortgage"))

    result = intake(state, llm=fake_llm)

    assert "stage" not in result
    assert result["application"] == {"product": "mortgage"}


def test_intake_rederives_the_financed_amount_on_resimulation():
    """"e se eu desse mais entrada?" has to move the financed amount.

    Deriving `requested_amount` only when the *merged* application lacks one
    pins it to whatever the first turn computed: the down payment changes and
    the LTV, the instalment and the decision all stay put. Re-simulation is the
    reason customer turns always route back to `intake` (SDD 05 §3), so this is
    the node's central behaviour, not an edge case.
    """
    prior = {
        "product": "mortgage",
        "asset_value": 400_000.0,
        "down_payment": 180_000.0,
        "term_months": 360,
        "requested_amount": 220_000.0,
    }
    state = _base_state(application=prior, messages=[HumanMessage("e se a entrada fosse 100 mil?")])
    fake_llm = _FakeStructuredLLM(_ExtractedFields(down_payment=100_000.0))

    result = intake(state, llm=fake_llm)

    assert result["application"]["down_payment"] == 100_000.0
    assert result["application"]["requested_amount"] == pytest.approx(300_000.0)


def test_intake_honours_an_explicitly_stated_financed_amount():
    prior = {
        "product": "mortgage",
        "asset_value": 400_000.0,
        "down_payment": 180_000.0,
        "term_months": 360,
        "requested_amount": 220_000.0,
    }
    state = _base_state(application=prior, messages=[HumanMessage("quero financiar 250 mil")])
    fake_llm = _FakeStructuredLLM(_ExtractedFields(requested_amount=250_000.0))

    result = intake(state, llm=fake_llm)

    assert result["application"]["requested_amount"] == pytest.approx(250_000.0)


def test_intake_flags_solve_financed_max_term_without_requiring_a_stale_term():
    """"Qual o valor máximo que eu consigo financiar, com o prazo máximo?" must
    be flagged even though `term_months` is not a fresh fact this turn — the
    whole point of this intent is that the term is itself unresolved, not
    reused from whatever the frontend's form default or an earlier turn left
    behind (the regression this covers: it silently stayed at 48).
    """
    prior = {
        "customer_id": "CUST-0001",
        "product": "auto",
        "down_payment": 16_000.0,
        "term_months": 48,
        "purpose": "Compra de veículo",
    }
    state = _base_state(
        application=prior,
        messages=[HumanMessage("qual o valor máximo que eu consigo financiar, com o prazo máximo?")],
    )
    fake_llm = _FakeStructuredLLM(_ExtractedFields(intent="solve_financed_max_term"))

    result = intake(state, llm=fake_llm)

    assert result["application"]["_intent"] == "solve_financed_max_term"


def test_credit_calculator_solves_financed_for_the_true_max_term():
    """Regression test for the max-term bug: the stale `term_months: 48` on
    the application must be replaced by POL-007's age-derived ceiling, not
    left untouched the way a plain `solve_financed` would.
    """
    application = {
        "product": "auto",
        "down_payment": 16_000.0,
        "term_months": 48,
        "_intent": "solve_financed_max_term",
    }
    profile = {
        "birth_date": "1990-04-17",
        "credit": {"internal_score": 782, "existing_monthly_debt": 0.0},
        "income": {"net_monthly": 11_200.0},
    }
    state = _base_state(application=application, profile=profile)

    result = credit_calculator(state)
    solved = result["application"]

    policy = POLICIES["auto"]
    current_age = age_at_maturity(profile["birth_date"], 0, date.today())
    expected_term = max_term_by_age(policy.age_at_maturity_limit.value, current_age)
    expected_financed = max_financeable(
        product="auto",
        down_payment=16_000.0,
        term_months=expected_term,
        net_income=11_200.0,
        existing_debt=0.0,
        score=782,
        dti_limit=policy.dti_auto_approval_limit.value,
        ltv_limit=policy.ltv_auto_approval_limit.value,
        amount_limit=policy.amount_auto_approval_limit.value,
    )

    assert solved["term_months"] == expected_term
    assert solved["term_months"] != 48
    assert solved["requested_amount"] == pytest.approx(expected_financed)
    assert solved["asset_value"] == pytest.approx(expected_financed + 16_000.0)


def test_intake_flags_the_manual_approval_band_explicitly():
    prior = {
        "customer_id": "CUST-0001",
        "product": "mortgage",
        "down_payment": 100_000.0,
        "term_months": 360,
        "purpose": "Compra de imóvel",
    }
    state = _base_state(
        application=prior,
        messages=[HumanMessage("e sem aprovação automática, qual o valor máximo?")],
    )
    fake_llm = _FakeStructuredLLM(_ExtractedFields(intent="solve_financed_manual"))

    result = intake(state, llm=fake_llm)

    assert result["application"]["_intent"] == "solve_financed_manual"


def test_credit_calculator_solves_against_manual_not_automatic_limits():
    application = {
        "product": "mortgage",
        "down_payment": 100_000.0,
        "term_months": 360,
        "purpose": "Compra de imóvel",
        "_intent": "solve_financed_manual",
    }
    profile = {
        "birth_date": "1990-04-17",
        "credit": {"internal_score": 782, "existing_monthly_debt": 1_350.0},
        "income": {"net_monthly": 11_200.0, "verified": True},
    }

    result = credit_calculator(_base_state(application=application, profile=profile))
    solved = result["application"]
    policy = POLICIES["mortgage"]
    expected = max_financeable(
        product="mortgage",
        down_payment=100_000.0,
        term_months=360,
        net_income=11_200.0,
        existing_debt=1_350.0,
        score=782,
        dti_limit=policy.dti_absolute_limit.value,
        ltv_limit=policy.ltv_absolute_limit.value,
        amount_limit=policy.amount_manual_approval_limit.value,
    )

    assert solved["requested_amount"] == pytest.approx(expected)
    assert solved["requested_amount"] > policy.amount_auto_approval_limit.value
    assert result["calculation_context"]["approval_band"] == "manual"


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
        "asset_value": 400_000.0,
        "down_payment": 100_000.0,
        "requested_amount": 300_000.0,
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
        "asset_value": 400_000.0,
        "requested_amount": 300_000.0,
        "term_months": 360,
    }
    profile = {
        "credit": {"internal_score": 782, "existing_monthly_debt": 1350.0},
        "income": {"net_monthly": 11_200.0},
    }
    state = _base_state(application=application, profile=profile)

    result = credit_calculator(state)
    calc = result["calc"]

    assert calc["ltv"] == pytest.approx(0.75)
    assert calc["monthly_payment"] == pytest.approx(2658.78, abs=0.01)
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
        "asset_value": 400_000.0,
        "down_payment": 100_000.0,
        "term_months": 360,
    }
    calc = {"monthly_payment": 2658.78, "annual_rate": 0.106}
    decision = {
        "outcome": "manual_review",
        "reasons": ["LTV de 75% acima de 70%, limite da aprovação automática."],
        "policy_refs": ["POL-020", "POL-004"],
    }
    state = _base_state(application=application, calc=calc, decision=decision)
    fake_llm = FakeListChatModel(responses=["Sua parcela ficou em R$ 2.658,78."])

    result = customer_response(state, llm=fake_llm)

    assert "2.658,78" in result["messages"][0].content


# --- decision node (SDD 05 §1) ---------------------------------------------
# `decision` is the only node that writes `applications`. These run against
# real Atlas (SDD 14 §2) and clean up after themselves.


@pytest.fixture
def application_row():
    application_id = "APP-TEST-DECISION"
    db = get_db()
    db["applications"].insert_one(
        {
            "_id": application_id,
            "thread_id": application_id,
            "customer_id": "CUST-0001",
            "status": "draft",
            "latest_assessment": None,
        }
    )
    yield application_id
    db["applications"].delete_one({"_id": application_id})
    db["decisions_log"].delete_many({"application_id": application_id})


def _assessed(application_id, *, asset_value, down_payment, term_months=360):
    """Run `credit_calculator` then `decision` the way the graph does, against
    the real seeded profile for CUST-0001.
    """
    application = {
        "application_id": application_id,
        "customer_id": "CUST-0001",
        "product": "mortgage",
        "asset_value": asset_value,
        "down_payment": down_payment,
        "requested_amount": asset_value - down_payment,
        "term_months": term_months,
    }
    profile = get_db()["customer_profiles"].find_one({"_id": "CUST-0001"})
    state = _base_state(application=application, profile=profile)
    state["calc"] = credit_calculator(state)["calc"]
    return state, decision(state)


def test_decision_auto_approves_and_closes_the_thread(application_row):
    state, result = _assessed(application_row, asset_value=400_000.0, down_payment=180_000.0)

    assert result["decision"]["outcome"] == "auto_approved"
    assert result["stage"] == "closed"
    assert result["decision"]["reasons"]
    assert result["decision"]["policy_refs"]
    assert result["decision"]["breached_rules"] == []


def test_decision_routes_to_review_when_a_human_is_needed(application_row):
    state, result = _assessed(application_row, asset_value=400_000.0, down_payment=100_000.0)

    assert result["decision"]["outcome"] == "manual_review"
    assert result["stage"] == "review"
    assert "ltv_auto_approval_limit" in result["decision"]["breached_rules"]


def test_decision_denies_beyond_the_absolute_limits(application_row):
    """The DTI POL-004 calls "reprovação automática" — 448k over 360 months on
    CUST-0001's income lands at 47,5%.

    These are deliberately *not* the demo figures. An early draft of the demo
    used this combination for beat 4's manual review; it denies, which would
    leave beat 5 with nothing in Carlos's queue (SDD 16 §2).
    """
    state, result = _assessed(application_row, asset_value=560_000.0, down_payment=112_000.0)

    assert result["decision"]["outcome"] == "denied"
    assert result["stage"] == "closed"
    assert result["decision"]["breached_rules"] == ["dti_absolute_limit"]


def test_decision_writes_exactly_one_assessment_event(application_row):
    """SDD 05 acceptance — an assessed application produces exactly one
    `assessment` event in `decisions_log`.
    """
    _state, result = _assessed(application_row, asset_value=400_000.0, down_payment=180_000.0)

    events = list(get_db()["decisions_log"].find({"application_id": application_row}))
    assert len(events) == 1
    event = events[0]
    assert event["event_type"] == "assessment"
    assert event["seq"] == 1
    assert event["thread_id"] == application_row
    assert event["outcome"] == result["decision"]["outcome"]
    assert event["policy_refs"] == result["decision"]["policy_refs"]
    assert event["rationale"]


def test_decision_updates_the_application_row(application_row):
    _state, result = _assessed(application_row, asset_value=400_000.0, down_payment=100_000.0)

    doc = get_db()["applications"].find_one({"_id": application_row})
    assert doc["status"] == "manual_review"
    assert doc["latest_assessment"]["decision"] == result["decision"]
    assert doc["latest_assessment"]["calc"]["ltv"] == pytest.approx(0.75)
    assert doc["product"] == "mortgage"
    assert doc["asset_value"] == pytest.approx(400_000.0)
    assert doc["down_payment"] == pytest.approx(100_000.0)
    assert doc["requested_amount"] == pytest.approx(300_000.0)
    assert doc["term_months"] == 360


def test_new_assessment_invalidates_a_prior_contract(application_row):
    get_db()["applications"].update_one(
        {"_id": application_row},
        {
            "$set": {
                "final_decision": {"outcome": "approved"},
                "contract_status": "contracted",
                "contracted_at": "2026-08-13T12:00:00Z",
            }
        },
    )

    _assessed(application_row, asset_value=400_000.0, down_payment=100_000.0)

    doc = get_db()["applications"].find_one({"_id": application_row})
    assert "final_decision" not in doc
    assert "contract_status" not in doc
    assert "contracted_at" not in doc


def test_decision_seq_increments_across_resimulations(application_row):
    """Mariana re-simulating on the same thread appends, never overwrites — the
    trace panel reads `decisions_log` in `seq` order.
    """
    _assessed(application_row, asset_value=400_000.0, down_payment=180_000.0)
    _assessed(application_row, asset_value=400_000.0, down_payment=100_000.0)

    events = list(get_db()["decisions_log"].find({"application_id": application_row}).sort("seq", 1))
    assert [e["seq"] for e in events] == [1, 2]
    assert [e["outcome"] for e in events] == ["auto_approved", "manual_review"]
