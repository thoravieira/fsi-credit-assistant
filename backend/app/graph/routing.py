"""SDD 05 §3 — conditional-edge routing functions.

Pure functions, no I/O. Used by `graph/builder.py` in `add_conditional_edges`.
"""

from app.graph.state import AgentState


def route(state: AgentState) -> str:
    if state["persona"] == "analyst":
        return "precedent_search" if state["stage"] == "review" else "negotiation"
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
