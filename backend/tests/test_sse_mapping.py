"""SDD 11 §2-3 — SSE event mapping, tested against a fake compiled graph so
it does not need `graph.builder` (SDD 04/05, [OPUS], deferred).

Event shapes below (`updates` fires only on node completion, `messages`
yields `(chunk, metadata)`, `custom` is a raw dict) were confirmed by
introspecting a throwaway `StateGraph.astream()` run — not assumed from
documentation.
"""

from langchain_core.messages import AIMessageChunk

from app.main import stream_chat_events


class _FakeGraph:
    def __init__(self, events):
        self._events = events

    async def astream(self, payload, config=None, *, stream_mode=None):
        for mode, chunk in self._events:
            yield mode, chunk


async def _collect(graph):
    return [event async for event in stream_chat_events(graph, "APP-1", "customer", "oi")]


async def test_updates_become_started_and_finished_trace_events():
    graph = _FakeGraph([("updates", {"router": {}})])

    events = await _collect(graph)

    assert 'event: trace\ndata: {"node": "router", "status": "started"' in events[0]
    assert 'event: trace\ndata: {"node": "router", "status": "finished"' in events[1]


async def test_custom_events_merge_into_finished_detail():
    graph = _FakeGraph(
        [
            ("custom", {"op": "$vectorSearch", "collection": "credit_policies", "k": 4}),
            ("custom", {"hits": [{"id": "POL-014", "score": 0.83}]}),
            ("updates", {"policy_retrieval": {"policies": []}}),
        ]
    )

    events = await _collect(graph)
    finished = events[1]

    assert '"status": "finished"' in finished
    assert '"detail"' in finished
    assert "POL-014" in finished


async def test_messages_become_token_events():
    chunk = AIMessageChunk(content="Com entrada de 30%")
    graph = _FakeGraph([("messages", (chunk, {"langgraph_node": "customer_response"}))])

    events = await _collect(graph)

    assert events[0] == 'event: token\ndata: {"text": "Com entrada de 30%"}\n\n'


async def test_state_fires_once_immediately_before_done():
    graph = _FakeGraph(
        [("updates", {"decision": {"stage": "review", "calc": None, "decision": None}})]
    )

    events = await _collect(graph)

    assert events[-2].startswith("event: state\n")
    assert events[-1] == 'event: done\ndata: {"thread_id": "APP-1"}\n\n'
    assert sum(1 for e in events if e.startswith("event: state\n")) == 1
