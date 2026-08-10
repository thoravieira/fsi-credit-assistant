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
    return "complete" if app and all(app.get(f) is not None for f in required) else "incomplete"


def needs_approval(state: AgentState) -> str:
    return "await_approval" if state.get("pending_approval") else "end"
