"""SDD 05 §3 — conditional-edge routing functions.

Pure functions, no I/O. Used by `graph/builder.py` in `add_conditional_edges`.
"""

from app.graph.state import AgentState


def route(state: AgentState) -> str:
    if state["persona"] == "analyst":
        # A thread with no `stage` in its checkpoint yet — e.g. an
        # application seeded straight into `applications` rather than run
        # through the customer path first — is exactly the "haven't shown
        # the dossier" case `analyst_brief` marks by later setting
        # `stage="negotiation"`; treat it the same as `"review"`, not as
        # already-negotiated.
        return "negotiation" if state.get("stage") == "negotiation" else "precedent_search"
    return "intake"


def has_complete_application(state: AgentState) -> str:
    app = state.get("application")
    required = ("product", "asset_value", "down_payment", "term_months")
    # `purpose` is truthy-checked, not `is not None`: `POST /api/applications`
    # defaults it to `""` (CreateApplicationRequest), which would otherwise
    # slip past a `None` check and let a scenario run — or be solved for
    # (SDD 12 follow-up, item 2) — without ever having been asked for.
    return (
        "complete"
        if app and all(app.get(f) is not None for f in required) and app.get("purpose")
        else "incomplete"
    )


def needs_approval(state: AgentState) -> str:
    return "await_approval" if state.get("pending_approval") else "end"
