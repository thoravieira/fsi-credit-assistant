"""Small presentation-facing trace helpers.

Node-boundary updates arrive only after a LangGraph node finishes. Emitting a
custom start marker at the top of each node lets the UI truthfully show what is
running while the model, retrieval, or persistence work is still in progress.
Direct unit tests call nodes outside a graph, so the helper safely becomes a
no-op when no stream writer is available.
"""

from langgraph.config import get_stream_writer


def trace_started(node: str, **detail) -> None:
    try:
        writer = get_stream_writer()
    except RuntimeError:
        return
    event: dict = {"node": node, "status": "started"}
    if detail:
        event["detail"] = detail
    writer({"trace_event": event})


def trace_step(node: str, step: str, **detail) -> None:
    try:
        writer = get_stream_writer()
    except RuntimeError:
        return
    writer({"trace_event": {"node": node, "status": "step", "step": step, "detail": detail}})
