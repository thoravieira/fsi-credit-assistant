"""SDD 06 §2-3 — the case context the negotiation tools receive.

`AgentState` and `DeepAgentState` stay separate (SDD 06 §2), so the tools
cannot reach into graph state for the application under discussion. They get it
as LangGraph runtime **context** instead: a value injected by the framework,
fixed for the turn, and — crucially — invisible to the model. `ToolRuntime` is
stripped from the JSON schema the LLM sees, so the model chooses *which*
scenario to evaluate while the customer's income, score and asset value arrive
from the database untouched.

The object travels one turn and carries two things home:

- `simulated` — every scenario `recalculate_scenario` evaluated, so the wrapper
  node can lift deterministic results into `AgentState["scenarios"]` without
  the model retyping a single number;
- `emit` — the **parent** graph's stream writer.

That second one is not decoration. `create_deep_agent()` returns a
`CompiledStateGraph`, so it runs as a subgraph, and a subgraph's own
`get_stream_writer()` events never reach `graph.astream(...)` unless the caller
passes `subgraphs=True` — which would also flood the SSE stream with the
agent's internal `model`/`tools` node boundaries. Verified by introspection, not
assumed. Handing the tools the parent's writer keeps the trace panel honest at
tool granularity while the stream contract in SDD 11 §2 stays flat.
"""

from collections.abc import Callable
from dataclasses import dataclass, field


def _discard(event: dict) -> None:
    """Writer used when nothing is streaming — unit tests, and `/api/approve`,
    which resumes the graph with `ainvoke`.
    """


@dataclass
class NegotiationCase:
    application: dict
    profile: dict
    emit: Callable[[dict], None] = _discard
    simulated: list[dict] = field(default_factory=list)

    @property
    def product(self) -> str:
        return self.application.get("product", "mortgage")

    def step(self, name: str, **detail) -> None:
        """Announce a tool or subagent step on the parent graph's stream.

        The whole negotiation happens inside one LangGraph node, so the
        node-boundary trace events of SDD 11 §2 would show a single opaque
        eight-second `negotiation` step. SDD 06 §6 makes that latency tolerable
        by showing *what* is being waited on — which requires emitting from
        here, while it happens.
        """
        self.emit({"node": "negotiation", "step": name, "detail": detail})

    def token(self, text: str) -> None:
        """Forward a piece of the agent's answer to the parent graph's stream.

        Same reason as `step`, one level down: the agent's own tokens are
        stranded inside the subgraph, so without this the analyst waits in
        silence and then the whole answer lands at once.
        """
        if text:
            self.emit({"node": "negotiation", "token": text})
