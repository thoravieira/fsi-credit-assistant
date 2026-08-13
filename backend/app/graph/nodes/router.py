"""SDD 05 §1 — router node. The dispatch decision itself lives in
`graph/routing.route`, used as the conditional-edge function right after
this node. `router` is a no-op placeholder so the edge has a node to attach
to.
"""

from app.graph.state import AgentState
from app.runtime_trace import trace_started


def router(state: AgentState) -> dict:
    trace_started("router", persona=state.get("persona"))
    return {}
