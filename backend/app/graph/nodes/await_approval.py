"""SDD 06 §5 — the human gate, as architecture rather than as policy.

`interrupt()` suspends the graph *inside* this node and checkpoints it to
Atlas. The process can be killed here and the pause survives; `POST /api/approve`
resumes with `Command(resume=...)` and execution continues on the next line.

The answer to *"why isn't it fully automatic?"* is therefore structural, not a
promise: there is no edge from `negotiation` to `persist_decision` that does not
pass through this node, so the agent has no path to writing a decision that does
not pass through a human. It is visible as a paused step in the trace panel.

`deepagents` also offers `interrupt_on={"tool_name": True}` for per-tool
human-in-the-loop. Deliberately not used: the approval gate belongs to the
parent graph, where it appears in the architecture diagram and is wired to an
endpoint. Knowing the alternative exists is the Q&A answer; choosing this one is
the design.
"""

from langgraph.types import interrupt

from app.graph.state import AgentState


def await_approval(state: AgentState) -> dict:
    proposal = state["pending_approval"]
    verdict = interrupt(proposal)

    # The proposal carries what the agent argued — the scenario, the citations,
    # the rationale. The verdict carries what the human decided. `persist_decision`
    # writes both, so the audit record shows the recommendation *and* the ruling,
    # including when they differ.
    return {"pending_approval": None, "decision": {**proposal, **verdict}}
