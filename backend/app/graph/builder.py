"""SDD 04 §4 / 05 §2 — graph assembly.

Built **once per process**, in `main.py`'s `lifespan`. Never per request and
never per session: the compiled graph holds the checkpointer, and it is that
single long-lived object on Atlas — not anything in this process's memory —
that makes the kill-and-resume beat work (SDD 07 §3).

Read the two branches below as the architecture argument they are. The customer
path is a **workflow**: seven fixed steps, no model deciding what happens next,
cheap and auditable, and it serves ~90% of requests. The analyst path ends in an
**agent**, because "which credit structure clears policy for this customer" is
genuinely open-ended. Same graph, same thread, same database — the boundary is
drawn on cost and auditability rather than on which tool is newest.

`router` is deterministic Python. It is never an LLM.
"""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore

from app.agent.negotiation import negotiation
from app.graph.nodes.analyst_brief import analyst_brief
from app.graph.nodes.await_approval import await_approval
from app.graph.nodes.credit_calculator import credit_calculator
from app.graph.nodes.customer_response import customer_response
from app.graph.nodes.decision import decision
from app.graph.nodes.intake import intake
from app.graph.nodes.load_context import load_context
from app.graph.nodes.persist_decision import persist_decision
from app.graph.nodes.policy_retrieval import policy_retrieval
from app.graph.nodes.precedent_search import precedent_search
from app.graph.nodes.router import router
from app.graph.routing import has_complete_application, needs_approval, route
from app.graph.state import AgentState


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
    builder.add_node("precedent_search", precedent_search)
    builder.add_node("analyst_brief", analyst_brief)
    builder.add_node("negotiation", negotiation)
    builder.add_node("await_approval", await_approval)
    builder.add_node("persist_decision", persist_decision)

    builder.add_edge(START, "router")
    builder.add_conditional_edges(
        "router",
        route,
        {
            "intake": "intake",
            "precedent_search": "precedent_search",
            "negotiation": "negotiation",
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

    # Analyst path. Carlos's first turn lands on `precedent_search` and gets a
    # dossier; `analyst_brief` moves the stage to `negotiation`, so every turn
    # after that routes to the deep agent.
    builder.add_edge("precedent_search", "analyst_brief")
    builder.add_edge("analyst_brief", END)

    # The approval gate. Most negotiation turns end at END; only a turn that
    # produced a `pending_approval` continues, and it continues into an
    # `interrupt()`. There is no path from the agent to `persist_decision` that
    # skips a human — that is the guarantee, and it is an edge, not a promise.
    builder.add_conditional_edges(
        "negotiation",
        needs_approval,
        {"await_approval": "await_approval", "end": END},
    )
    builder.add_edge("await_approval", "persist_decision")
    builder.add_edge("persist_decision", END)

    # Both are `compile()` parameters (SDD 13 §5). The store is then reachable
    # from inside any node via `langgraph.config.get_store()`, so nodes do not
    # take it as an argument.
    return builder.compile(checkpointer=checkpointer, store=store)
