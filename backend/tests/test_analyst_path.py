"""SDD 05 §2 / 06 §5 — the analyst path through the compiled graph.

Runs against the real Atlas cluster: real `$vectorSearch` for precedents, a real
`interrupt()` checkpointed to `checkpoints`, a real embedding written into
`historical_cases`, real memories in `agent_memories`. Only the language models
are faked — the whole point of these assertions is that the persistence is not.
"""

from contextlib import ExitStack
from unittest.mock import patch

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from app.agent import negotiation as negotiation_module
from app.config import DEMO_ANALYST_ID
from app.db import get_db
from app.graph.builder import build_graph
from app.graph.prompts import load_prompt
from app.graph.tools.case import NegotiationCase
from app.graph.tools.scenario import check_open_finance_assets, recalculate_scenario
from app.memory.checkpointer import get_checkpointer
from app.memory.store import (
    analyst_decision_patterns_namespace,
    customer_facts_namespace,
    customer_preferences_namespace,
    get_store,
)
from deepagents import create_deep_agent
from tests.fakes import ScriptedChatModel, tool_call
from tests.test_negotiation_agent import APPLICATION, PROFILE

THREAD = "APP-TEST-ANALYST"
CUSTOMER = "CUST-TEST-ANALYST"
EXPECTED_CASE_ID = "CASE-TEST-ANALYST"


@pytest.fixture(scope="module")
def graph():
    return build_graph(checkpointer=get_checkpointer(), store=get_store())


@pytest.fixture
def thread():
    db = get_db()
    db["applications"].insert_one(
        {"_id": THREAD, "thread_id": THREAD, "customer_id": CUSTOMER, "status": "manual_review"}
    )
    yield THREAD

    db["applications"].delete_one({"_id": THREAD})
    db["decisions_log"].delete_many({"application_id": THREAD})
    db["historical_cases"].delete_one({"_id": EXPECTED_CASE_ID})
    for collection in ("checkpoints", "checkpoint_writes"):
        db[collection].delete_many({"thread_id": THREAD})

    # Memories are keyed by slug, and the analyst namespace is shared with the
    # demo — so clean up by evidence rather than by key, and leave anything a
    # rehearsal wrote alone.
    store = get_store()
    for namespace in (
        customer_preferences_namespace(CUSTOMER),
        customer_facts_namespace(CUSTOMER),
        analyst_decision_patterns_namespace(DEMO_ANALYST_ID),
    ):
        for item in store.search(namespace):
            if THREAD in (item.value.get("evidence_application_ids") or []):
                store.delete(namespace, item.key)


def _state(stage: str, message: str) -> dict:
    """The case as it stands when Carlos opens it: assessed, and sent to a
    human by the rules. `thread_id == application_id`, so in the demo this
    state arrives from Mariana's own conversation rather than from a payload.
    """
    return {
        "persona": "analyst",
        "stage": stage,
        "application": {**APPLICATION, "application_id": THREAD, "customer_id": CUSTOMER},
        "profile": PROFILE,
        "calc": {"monthly_payment": 2_800.0, "ltv": 0.75, "dti": 0.30, "annual_rate": 0.113,
                 "cet_annual": 0.129, "total_interest": 700_000.0, "schedule_preview": []},
        "decision": {"outcome": "manual_review", "reasons": ["LTV de 75% acima de 70%."],
                     "policy_refs": ["POL-020"], "breached_rules": ["ltv_auto_approval_limit"]},
        "messages": [HumanMessage(message)],
    }


def _fake_negotiation_agent(script: list[AIMessage]):
    return create_deep_agent(
        model=ScriptedChatModel(script),
        tools=[recalculate_scenario, check_open_finance_assets],
        system_prompt=load_prompt("negotiation"),
        context_schema=NegotiationCase,
        name="negotiation",
    )


def _run(graph, payload, script=None):
    """Stream a turn and return (nodes visited, custom events, final state)."""
    config = {"configurable": {"thread_id": THREAD}}
    visited, custom, final = [], [], {}

    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "app.graph.nodes.analyst_brief._default_llm",
                return_value=FakeListChatModel(responses=["Dossiê: LTV de 75% (POL-020)."]),
            )
        )
        if script is not None:
            stack.enter_context(
                patch.object(
                    negotiation_module,
                    "get_negotiation_agent",
                    return_value=_fake_negotiation_agent(script),
                )
            )
        for mode, chunk in graph.stream(
            payload, config=config, stream_mode=["updates", "custom"]
        ):
            if mode == "custom":
                custom.append(chunk)
                continue
            for node, update in chunk.items():
                visited.append(node)
                # `__interrupt__` carries a tuple of `Interrupt`s, not a state
                # update — see the same guard in `main.py`.
                if isinstance(update, dict):
                    final.update(update)
    return visited, custom, final


def test_analyst_entry_produces_a_dossier_and_opens_the_negotiation(graph, thread):
    """SDD 05 §3 — an analyst turn at `stage="review"` routes to
    `precedent_search`, and `analyst_brief` is what moves the stage on, so every
    later turn reaches the deep agent instead of rebuilding the dossier.
    """
    visited, custom, final = _run(graph, _state("review", "qual o histórico deste caso?"))

    assert visited == ["router", "precedent_search", "analyst_brief"]
    assert final["stage"] == "negotiation"
    assert final["precedents"]  # real $vectorSearch hits
    # SDD 05 acceptance: the trace carries the matched ids and scores.
    assert any("hits" in event for event in custom)
    assert (
        get_db()["decisions_log"].count_documents(
            {"application_id": THREAD, "event_type": "recommendation"}
        )
        == 1
    )


def test_a_negotiation_turn_streams_tool_steps_and_stops_short_of_a_decision(graph, thread):
    """SDD 06 §6 — the tool steps reach the *parent* stream. A subgraph's own
    writer does not, which is why `NegotiationCase` carries the parent's.
    """
    script = [
        tool_call("recalculate_scenario", "c1", down_payment=168_000.0),
        AIMessage("Com entrada de R$ 168.000,00 o LTV cai para 58% (POL-020)."),
    ]
    visited, custom, final = _run(graph, _state("negotiation", "e se a entrada subisse?"), script)

    assert visited == ["router", "negotiation"]
    assert "await_approval" not in visited
    steps = [event for event in custom if "step" in event]
    assert [s["step"] for s in steps] == ["recalculate_scenario"]
    assert final["scenarios"][0]["calc"]["ltv"] == pytest.approx(0.58)


def test_approval_is_a_graph_pause_and_only_a_human_resume_writes_the_decision(graph, thread):
    """SDD 06 acceptance — saying "aprovar" reaches `await_approval` and writes
    no final decision until `/api/approve` resumes the thread.

    Both halves matter. The pause is checkpointed to Atlas, so this is also the
    mechanism behind the kill-and-resume beat.
    """
    db = get_db()
    config = {"configurable": {"thread_id": THREAD}}
    script = [
        tool_call("recalculate_scenario", "c1", down_payment=168_000.0),
        AIMessage("Recomendo aprovar com condições: LTV de 58% (POL-020), renda "
                  "comprovada (POL-012), com compartilhamento via Open Finance."),
    ]

    visited, _custom, _final = _run(graph, _state("negotiation", "pode aprovar"), script)

    # `await_approval` never *finishes*: it suspends inside `interrupt()`, so
    # the stream reports `__interrupt__` and the graph's next step is the node
    # still waiting to complete.
    assert visited == ["router", "negotiation", "__interrupt__"]
    assert graph.get_state(config).next == ("await_approval",)
    assert db["decisions_log"].count_documents(
        {"application_id": THREAD, "event_type": "final_decision"}
    ) == 0
    assert db["historical_cases"].count_documents({"_id": EXPECTED_CASE_ID}) == 0

    # `POST /api/approve` — the human resume.
    result = graph.invoke(
        Command(resume={"outcome": "approved_with_conditions",
                        "conditions": ["compartilhamento de ativos via Open Finance"]}),
        config=config,
    )

    assert result["stage"] == "closed"
    assert result["pending_approval"] is None
    # The proposal and the verdict are merged, so the record shows both what the
    # agent argued and what the human ruled.
    assert result["decision"]["outcome"] == "approved_with_conditions"
    assert result["decision"]["policy_refs"] == ["POL-020", "POL-012"]
    persisted = db["applications"].find_one({"_id": THREAD})
    assert persisted["status"] == "approved_with_conditions"
    assert persisted["asset_value"] == pytest.approx(400_000.0)
    assert persisted["down_payment"] == pytest.approx(168_000.0)
    assert persisted["requested_amount"] == pytest.approx(232_000.0)
    assert persisted["term_months"] == 360
    assert result["application"]["requested_amount"] == pytest.approx(232_000.0)
    assert result["application"]["status"] == "approved_with_conditions"

    logged = db["decisions_log"].find_one({"application_id": THREAD, "event_type": "final_decision"})
    assert logged["actor"] == {"type": "analyst", "id": DEMO_ANALYST_ID}
    assert logged["prompt_version"] and logged["model"]

    # SDD 08 §4 — the precedent loop: the case just decided is retrievable now.
    precedent = db["historical_cases"].find_one({"_id": EXPECTED_CASE_ID})
    assert len(precedent["embedding"]) == 1024
    assert precedent["ltv_band"] == "low"
    assert "Open Finance" in precedent["summary"]
    assert precedent["structured"]["requested_amount"] == pytest.approx(232_000.0)

    # SDD 07 §2 — all three namespaces written, from what actually happened.
    store = get_store()
    dti = result["decision"]["scenario"]["calc"]["dti"]
    assert store.get(customer_preferences_namespace(CUSTOMER), "estrutura-aceita")
    assert store.get(customer_facts_namespace(CUSTOMER), "renda-e-vinculo")
    assert store.get(
        analyst_decision_patterns_namespace(DEMO_ANALYST_ID),
        f"mortgage-dti-ate-{round(dti * 100)}",
    )
