"""SDD 11 — the API, tested against real Atlas (SDD 14 §2).

Two groups. The DB-only endpoints use the module-level `client`, deliberately
*not* entered as a context manager, so `lifespan` never runs and they cost no
graph compilation. The `/api/chat` group enters `TestClient(app)` as a context
manager on purpose: that runs `lifespan`, which compiles the real graph.
"""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage

from app.db import get_db
from app.graph.nodes.intake import _ExtractedFields
from app.main import _hydrate_application, _hydrate_decision_context, app

client = TestClient(app)


# --- hydration helpers (pure, no I/O) ---------------------------------------
# SDD 04 §1 / item 10 — an application seeded straight into `applications`
# (Part B of the demo data) has never run through the graph, so its
# checkpoint has neither `application` patches nor `calc`/`decision` yet.
# These must fall back to the stored row without ever clobbering a live
# checkpoint's own state — the exact bug this covers crashed `/api/chat` for
# every one of the 50 seeded applications the first time an analyst opened one
# (`route()` did `state["stage"]` on a checkpoint that had no `stage` key at
# all — see `test_routing.py`).


def test_hydrate_application_keeps_checkpoint_inputs_but_database_status_wins():
    row = {
        "_id": "APP-X", "customer_id": "CUST-X", "product": "mortgage",
        "asset_value": 400_000.0, "down_payment": 100_000.0, "requested_amount": 300_000.0,
        "term_months": 360, "purpose": "compra", "status": "manual_review",
    }
    existing = {
        "down_payment": 150_000.0,
        "status": "approved_with_conditions",
    }  # a patch plus a stale decision from a prior checkpoint

    result = _hydrate_application(row, existing)

    assert result["down_payment"] == 150_000.0
    assert result["status"] == "manual_review"


def test_hydrate_application_returns_existing_untouched_when_the_row_is_missing():
    assert _hydrate_application(None, {"foo": "bar"}) == {"foo": "bar"}


def test_hydrate_decision_context_falls_back_to_the_stored_assessment_when_the_checkpoint_is_empty():
    row = {"latest_assessment": {"calc": {"ltv": 0.7}, "decision": {"outcome": "manual_review"}}}

    calc, decision = _hydrate_decision_context(row, None, None)

    assert calc == {"ltv": 0.7}
    assert decision == {"outcome": "manual_review"}


def test_hydrate_decision_context_prefers_the_final_decision_over_the_original_assessment():
    row = {
        "latest_assessment": {"calc": {"ltv": 0.7}, "decision": {"outcome": "manual_review"}},
        "final_decision": {"outcome": "approved_with_conditions"},
    }

    _calc, decision = _hydrate_decision_context(row, None, None)

    assert decision == {"outcome": "approved_with_conditions"}


def test_hydrate_decision_context_never_overwrites_a_matching_live_checkpoint():
    row = {
        "status": "manual_review",
        "latest_assessment": {"calc": {"ltv": 0.99}, "decision": {"outcome": "denied"}},
    }

    calc, decision = _hydrate_decision_context(row, {"ltv": 0.5}, {"outcome": "manual_review"})

    assert calc == {"ltv": 0.5}
    assert decision == {"outcome": "manual_review"}


def test_hydrate_decision_context_replaces_a_stale_human_decision_after_resimulation():
    row = {
        "status": "manual_review",
        "latest_assessment": {"calc": {"ltv": 0.75}, "decision": {"outcome": "manual_review"}},
        "final_decision": {"outcome": "approved_with_conditions"},
    }

    calc, decision = _hydrate_decision_context(
        row,
        {"ltv": 0.58},
        {"outcome": "approved_with_conditions"},
    )

    assert calc == {"ltv": 0.75}
    assert decision == {"outcome": "manual_review"}


def test_hydrate_decision_context_uses_the_final_scenario_calc_after_approval():
    final = {
        "outcome": "approved",
        "scenario": {"calc": {"ltv": 0.69, "dti": 0.30}},
    }
    row = {
        "status": "approved",
        "latest_assessment": {"calc": {"ltv": 0.78, "dti": 0.40}},
        "final_decision": final,
    }

    calc, decision = _hydrate_decision_context(
        row,
        {"ltv": 0.78, "dti": 0.40},
        final,
    )

    assert calc == {"ltv": 0.69, "dti": 0.30}
    assert decision == final


@pytest.fixture
def created_application():
    body = {
        "customer_id": "CUST-0001",
        "product": "mortgage",
        "asset_value": 400_000.0,
        "down_payment": 100_000.0,
        "term_months": 360,
        "purpose": "teste automatizado",
    }
    response = client.post("/api/applications", json=body)
    application_id = response.json()["application_id"]
    yield application_id, body
    get_db()["applications"].delete_one({"_id": application_id})


def test_create_application_returns_id_and_persists(created_application):
    application_id, body = created_application

    assert application_id.startswith("APP-")

    doc = get_db()["applications"].find_one({"_id": application_id})
    assert doc["thread_id"] == application_id
    assert doc["status"] == "draft"
    assert doc["requested_amount"] == pytest.approx(300_000.0)


def test_list_applications_filters_by_status(created_application):
    application_id, _ = created_application

    response = client.get("/api/applications", params={"status": "draft"})

    ids = [a["_id"] for a in response.json()["applications"]]
    assert application_id in ids


def test_get_application_by_id(created_application):
    application_id, _ = created_application

    response = client.get(f"/api/applications/{application_id}")

    assert response.status_code == 200
    assert response.json()["_id"] == application_id


def test_get_application_404_when_missing():
    response = client.get("/api/applications/APP-DOES-NOT-EXIST")
    assert response.status_code == 404


def test_get_trace_for_fresh_thread_is_empty(created_application):
    application_id, _ = created_application

    response = client.get(f"/api/trace/{application_id}")

    assert response.json() == {"thread_id": application_id, "events": []}


def test_health_reports_index_readiness_not_just_connectivity():
    response = client.get("/api/health")
    body = response.json()

    assert body["connected"] is True
    assert set(body["indexes"]) == {"credit_policies", "historical_cases", "agent_memories"}
    for status in body["indexes"].values():
        assert status["exists"] is True


# --- /api/chat, SSE (SDD 11 §2-3) ------------------------------------------
# Entering `TestClient(app)` as a context manager runs `lifespan`, which
# compiles the real graph against the real checkpointer and store. Only the two
# LLM factories are faked (SDD 14 §2): everything else here is a live Atlas
# round trip, which is the point — the trace panel is only worth showing if the
# events behind it are real (SDD 11 §4).


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        if not block.strip():
            continue
        name = data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line.removeprefix("event: ")
            elif line.startswith("data: "):
                data = json.loads(line.removeprefix("data: "))
        if name is not None:
            events.append((name, data))
    return events


@pytest.fixture
def chat_thread():
    body = {
        "customer_id": "CUST-0001",
        "product": "mortgage",
        "asset_value": 400_000.0,
        "down_payment": 100_000.0,
        "term_months": 360,
        "purpose": "teste SSE",
    }
    application_id = client.post("/api/applications", json=body).json()["application_id"]
    yield application_id
    db = get_db()
    db["applications"].delete_one({"_id": application_id})
    db["decisions_log"].delete_many({"application_id": application_id})
    for collection in ("checkpoints", "checkpoint_writes"):
        db[collection].delete_many({"thread_id": application_id})


def _chat(thread_id: str, message: str, *, answer: str) -> list[tuple[str, dict]]:
    extractor = _FakeExtractor(
        _ExtractedFields(
            product="mortgage", asset_value=400_000.0, down_payment=100_000.0, term_months=360
        )
    )
    with (
        patch("app.graph.nodes.intake._default_llm", return_value=extractor),
        patch(
            "app.graph.nodes.customer_response._default_llm",
            return_value=FakeListChatModel(responses=[answer]),
        ),
        TestClient(app) as running_client,
    ):
        response = running_client.post(
            "/api/chat",
            json={"thread_id": thread_id, "persona": "customer", "message": message},
        )
    assert response.status_code == 200
    return _parse_sse(response.text)


class _FakeExtractor:
    def __init__(self, result):
        self._result = result

    def with_structured_output(self, schema):
        return self

    def invoke(self, messages):
        return self._result


def test_chat_streams_all_four_event_types(chat_thread):
    """SDD 11 acceptance — `curl -N -X POST /api/chat` streams all four types.
    This is the automated form of the command in `docs/demo-script.md`.
    """
    events = _chat(chat_thread, "Apartamento de 400 mil com 100 mil de entrada", answer="Olá!")

    assert {name for name, _ in events} == {"trace", "token", "state", "done"}


def test_chat_tokens_reconstruct_exactly_the_answer(chat_thread):
    """The concatenated `token` stream is the answer, once — no `intake`
    extraction JSON in front of it and no duplicate copy behind it.
    """
    answer = "Sua proposta seguirá para análise manual."
    events = _chat(chat_thread, "Apartamento de 400 mil com 100 mil de entrada", answer=answer)

    streamed = "".join(data["text"] for name, data in events if name == "token")
    assert streamed == answer


def test_chat_trace_events_follow_real_node_execution(chat_thread):
    """SDD 11 §4 — every trace event originates from actual graph execution."""
    events = _chat(chat_thread, "Apartamento de 400 mil com 100 mil de entrada", answer="Olá!")

    finished = [data["node"] for name, data in events if name == "trace" and data["status"] == "finished"]
    assert finished == [
        "router",
        "intake",
        "load_context",
        "policy_retrieval",
        "credit_calculator",
        "decision",
        "customer_response",
    ]

    started = [data["node"] for name, data in events if name == "trace" and data["status"] == "started"]
    assert started == finished


def test_chat_node_timings_are_measured(chat_thread):
    """SDD 11 acceptance — timings measured, never estimated. The retrieval and
    LLM nodes do real I/O, so at least one of them must show real elapsed time.
    """
    events = _chat(chat_thread, "Apartamento de 400 mil com 100 mil de entrada", answer="Olá!")

    timings = {
        data["node"]: data["ms"]
        for name, data in events
        if name == "trace" and data["status"] == "finished"
    }
    assert all(isinstance(ms, int) and ms >= 0 for ms in timings.values())
    assert timings["policy_retrieval"] > 0


def test_chat_emits_retrieval_detail_with_real_ids(chat_thread):
    """SDD 11 acceptance — `policy_retrieval` emits real matched IDs and scores."""
    events = _chat(chat_thread, "Apartamento de 400 mil com 100 mil de entrada", answer="Olá!")

    detail = next(
        data["detail"]
        for name, data in events
        if name == "trace" and data["node"] == "policy_retrieval" and "detail" in data
    )
    assert detail["op"] == "$vectorSearch"
    assert detail["collection"] == "credit_policies"
    assert detail["hits"]
    assert all(hit["id"].startswith("POL-") for hit in detail["hits"])


def test_chat_state_event_fires_once_immediately_before_done(chat_thread):
    """SDD 11 §2 — emitting `state` per node would flicker the UI through
    intermediate states that were never real conclusions.
    """
    events = _chat(chat_thread, "Apartamento de 400 mil com 100 mil de entrada", answer="Olá!")

    names = [name for name, _ in events]
    assert names.count("state") == 1
    assert names[-2:] == ["state", "done"]

    _name, state = events[-2]
    assert state["stage"] == "review"
    assert state["decision"]["outcome"] == "manual_review"
    assert state["calc"]["ltv"] == pytest.approx(0.75)
    assert state["decision"]["policy_refs"]


def test_chat_hydrates_the_application_from_the_thread_id(chat_thread):
    """SDD 04 §1 / 11 §3 — `/api/chat` carries only a thread id, so this
    endpoint is what turns it into `application_id` + `customer_id`. Without
    that, `decision` never finds an application and `load_context` never finds
    a profile.
    """
    _chat(chat_thread, "Apartamento de 400 mil com 100 mil de entrada", answer="Olá!")

    events = list(get_db()["decisions_log"].find({"application_id": chat_thread}))
    assert len(events) == 1
    assert events[0]["thread_id"] == chat_thread

    doc = get_db()["applications"].find_one({"_id": chat_thread})
    assert doc["status"] == "manual_review"
    assert doc["latest_assessment"]["decision"]["outcome"] == "manual_review"


def test_contract_keeps_the_human_verdict_and_filters_customer_history(chat_thread):
    _chat(chat_thread, "Simular a proposta.", answer="A proposta seguirá para análise manual.")
    final_decision = {
        "outcome": "approved",
        "policy_refs": ["POL-020", "POL-004"],
        "scenario": {
            "inputs": {
                "asset_value": 326_795.20,
                "amount": 226_795.20,
                "down_payment": 100_000.0,
                "term_months": 360,
            },
            "calc": {"ltv": 0.694, "dti": 0.30, "monthly_payment": 2_009.99},
        },
    }
    get_db()["applications"].update_one(
        {"_id": chat_thread},
        {"$set": {"status": "approved", "final_decision": final_decision}},
    )

    with TestClient(app) as running_client:
        graph = running_client.app.state.graph
        graph.update_state(
            {"configurable": {"thread_id": chat_thread}},
            {
                "messages": [
                    HumanMessage("Pergunta interna.", additional_kwargs={"persona": "analyst"}),
                    AIMessage("Parecer interno.", additional_kwargs={"persona": "analyst"}),
                ]
            },
        )

        response = running_client.post("/api/contract", json={"thread_id": chat_thread})
        assert response.status_code == 200
        second = running_client.post("/api/contract", json={"thread_id": chat_thread})
        assert second.status_code == 200

        customer_history = running_client.get(
            f"/api/history/{chat_thread}", params={"persona": "customer"}
        ).json()["messages"]
        analyst_history = running_client.get(
            f"/api/history/{chat_thread}", params={"persona": "analyst"}
        ).json()["messages"]

    persisted = get_db()["applications"].find_one({"_id": chat_thread})
    assert persisted["status"] == "approved"
    assert persisted["final_decision"] == final_decision
    assert persisted["contract_status"] == "contracted"
    assert persisted["contracted_at"] is not None
    assert all("intern" not in message["text"].lower() for message in customer_history)
    assert [message["text"] for message in analyst_history] == ["Pergunta interna.", "Parecer interno."]
    assert sum("Aceito contratar" in message["text"] for message in customer_history) == 1
    assert sum("Aceite registrado" in message["text"] for message in customer_history) == 1


def test_trace_endpoint_returns_the_persisted_events(chat_thread):
    _chat(chat_thread, "Apartamento de 400 mil com 100 mil de entrada", answer="Olá!")

    response = client.get(f"/api/trace/{chat_thread}")
    events = response.json()["events"]

    assert [e["event_type"] for e in events] == ["assessment"]
    assert events[0]["seq"] == 1


def test_approve_is_still_blocked_on_the_analyst_path(chat_thread):
    """SDD 11 acceptance — "/api/approve resumes an interrupted thread and the
    graph reaches `persist_decision`" cannot be asserted yet: `await_approval`
    and `persist_decision` are session 6, so no thread ever has a pending
    `interrupt()` to resume.

    `Command(resume=...)` against a thread with nothing suspended does not
    resume; it starts a fresh run whose only input is the resume value, so
    `router` gets a state with no `persona`. This is the canary for session 6 —
    replace it with a real approve test once `await_approval` lands.
    """
    with pytest.raises(KeyError, match="persona"):
        with TestClient(app) as running_client:
            running_client.post(
                "/api/approve",
                json={"thread_id": chat_thread, "resume": {"approved": True}},
            )
