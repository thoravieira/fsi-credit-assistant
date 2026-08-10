"""SDD 11 — endpoints that don't need the compiled graph, tested against real
Atlas (SDD 14 §2). `TestClient(app)` used without a `with` block deliberately
does not trigger `lifespan`, so these run today even though `graph.builder`
(SDD 04/05, [OPUS]) does not exist yet — see main.py's module docstring.
"""

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app

client = TestClient(app)


@pytest.fixture
def created_application():
    body = {
        "customer_id": "CUST-0001",
        "product": "mortgage",
        "asset_value": 560_000.0,
        "down_payment": 112_000.0,
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
    assert doc["requested_amount"] == pytest.approx(448_000.0)


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


def test_chat_and_approve_blocked_on_graph_builder():
    """SDD 04 §4 — `graph.builder.build_graph` is deferred to the Opus
    session. `/api/chat` and `/api/approve` need the compiled graph, built in
    `lifespan`, so they only fail once that lifespan actually runs. This
    documents the block; replace with real SSE/approve tests once
    builder.py lands.
    """
    with pytest.raises(ModuleNotFoundError):
        with TestClient(app) as running_client:
            running_client.post(
                "/api/chat",
                json={"thread_id": "APP-X", "persona": "customer", "message": "oi"},
            )
