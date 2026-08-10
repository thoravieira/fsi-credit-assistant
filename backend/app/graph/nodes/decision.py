"""SDD 05 §1 — decision node. Applies `domain/rules.py` and is the only node
that writes `applications`.

`domain.rules.evaluate` is deferred to the Opus session (SDD 10 §3). This
node is written against that interface — the seam the next session fills in:

    evaluate(application: CreditApplication, calc: CalcResult, profile: dict) -> Decision

Importing this module raises `ModuleNotFoundError` until `domain/rules.py`
exists.
"""

from datetime import datetime, timezone

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
                "status": result["outcome"],
                "updated_at": now,
                "latest_assessment": {"calc": calc, "decision": result},
            }
        },
    )

    seq = db["decisions_log"].count_documents({"application_id": application_id}) + 1
    db["decisions_log"].insert_one(
        {
            "application_id": application_id,
            "thread_id": application_id,
            "seq": seq,
            "event_type": "assessment",
            "actor": {"type": "agent", "id": "system"},
            "calc": calc,
            "outcome": result["outcome"],
            "policy_refs": result["policy_refs"],
            "rationale": " ".join(result["reasons"]),
            "created_at": now,
        }
    )

    stage = "review" if result["outcome"] == "manual_review" else "closed"
    return {"decision": result, "stage": stage}
