"""SDD 05 §1 — decision node. Applies `domain/rules.py`.

Writes an `assessment` event **on every path, including automatic approvals**,
before the customer sees any answer. An audit trail that only covers the cases
a human touched is not an audit trail (SDD 02 §6).
"""

from datetime import datetime, timezone

from app.audit import append_event
from app.db import get_db
from app.domain.rules import evaluate
from app.graph.state import AgentState


def decision(state: AgentState) -> dict:
    application = state["application"]
    calc = state["calc"]
    profile = state.get("profile") or {}

    result = evaluate(application, calc, profile)

    db = get_db()
    now = datetime.now(timezone.utc)
    application_id = application["application_id"]

    db["applications"].update_one(
        {"_id": application_id},
        {
            "$set": {
                "product": application["product"],
                "asset_value": application["asset_value"],
                "down_payment": application["down_payment"],
                "requested_amount": application["requested_amount"],
                "term_months": application["term_months"],
                "purpose": application.get("purpose", ""),
                "status": result["outcome"],
                "updated_at": now,
                "latest_assessment": {"calc": calc, "decision": result},
            },
            # A new assessment supersedes both a prior human resolution and
            # any acceptance of that old proposal. The audit log keeps the
            # history, while the live row must describe only the new offer.
            "$unset": {
                "final_decision": "",
                "contract_status": "",
                "contracted_at": "",
            },
        },
    )

    append_event(
        application_id,
        "assessment",
        {"type": "agent", "id": "system"},
        calc=calc,
        outcome=result["outcome"],
        policy_refs=result["policy_refs"],
        rationale=" ".join(result["reasons"]),
    )

    stage = "review" if result["outcome"] == "manual_review" else "closed"
    return {"decision": result, "stage": stage}
