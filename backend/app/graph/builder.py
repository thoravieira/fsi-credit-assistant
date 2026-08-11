"""SDD 04 §4 / 05 §2 — graph assembly.

Built **once per process**, in `main.py`'s `lifespan`. Never per request and
never per session: the compiled graph holds the checkpointer, and it is that
single long-lived object on Atlas — not anything in this process's memory —
that makes the kill-and-resume beat work (SDD 07 §3).

Scope is the customer path (`router` → `customer_response`). The analyst path
(`precedent_search`, `analyst_brief`, `negotiation`, `await_approval`,
`persist_decision`) is SDD 06, execution session 6; until it lands, both
analyst branches of `routing.route` resolve to `_analyst_path_pending`, which
fails loudly rather than silently routing a persona nowhere.
"""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore

from app.graph.nodes.credit_calculator import credit_calculator
from app.graph.nodes.customer_response import customer_response
from app.graph.nodes.decision import decision
from app.graph.nodes.intake import intake
from app.graph.nodes.load_context import load_context
from app.graph.nodes.policy_retrieval import policy_retrieval
from app.graph.nodes.router import router
from app.graph.routing import has_complete_application, route
from app.graph.state import AgentState

ANALYST_PATH_PENDING = "_analyst_path_pending"


def _analyst_path_pending(state: AgentState) -> dict:
    raise NotImplementedError(
        "analyst path not built yet — SDD 06, execution session 6 "
        f"(persona={state.get('persona')!r}, stage={state.get('stage')!r})"
    )


def build_graph(
    checkpointer: BaseCheckpointSaver, store: BaseStore
) -> CompiledStateGraph:
    builder = StateGraph(AgentState)

    builder.add_node("router", router)
    builder.add_node("intake", intake)
    builder.add_node("load_context", load_context)
    builder.add_node("policy_retrieval", policy_retrieval)
    builder.add_node("credit_calculator", credit_calculator)
    builder.add_node("decision", decision)
    builder.add_node("customer_response", customer_response)
    builder.add_node(ANALYST_PATH_PENDING, _analyst_path_pending)

    builder.add_edge(START, "router")
    builder.add_conditional_edges(
        "router",
        route,
        {
            "intake": "intake",
            "precedent_search": ANALYST_PATH_PENDING,
            "negotiation": ANALYST_PATH_PENDING,
        },
    )

    # Customer path. `intake` is the boundary between free text and typed
    # code, so it gets a conditional edge: an unconditional one would carry a
    # `None` amount into the calculator (SDD 05 §3).
    builder.add_conditional_edges(
        "intake",
        has_complete_application,
        {"complete": "load_context", "incomplete": "customer_response"},
    )
    builder.add_edge("load_context", "policy_retrieval")
    builder.add_edge("policy_retrieval", "credit_calculator")
    builder.add_edge("credit_calculator", "decision")
    builder.add_edge("decision", "customer_response")
    builder.add_edge("customer_response", END)

    builder.add_edge(ANALYST_PATH_PENDING, END)

    # Both are `compile()` parameters (SDD 13 §5). The store is then reachable
    # from inside any node via `langgraph.config.get_store()`, so nodes do not
    # take it as an argument.
    return builder.compile(checkpointer=checkpointer, store=store)
