"""SDD 11 §2-3 — SSE event mapping in isolation.

Driven by a fake compiled graph so each stream mode can be replayed exactly:
these assert the *mapping* from `astream` chunks onto the four SSE event types,
never that the real graph produces any particular chunk. `tests/test_main.py`
covers the round trip through the real graph.

Event shapes below (`updates` fires only on node completion, `messages`
yields `(chunk, metadata)`, `custom` is a raw dict) were confirmed by
introspecting a throwaway `StateGraph.astream()` run — not assumed from
documentation.
"""

import json
from dataclasses import dataclass, field

from langchain_core.messages import AIMessage, AIMessageChunk

from app.main import stream_approval_events, stream_chat_events


@dataclass
class _FakeSnapshot:
    values: dict = field(default_factory=dict)


class _FakeGraph:
    def __init__(self, events, state=None):
        self._events = events
        self._state = _FakeSnapshot(state or {})

    async def astream(self, payload, config=None, *, stream_mode=None):
        for mode, chunk in self._events:
            yield mode, chunk

    async def aget_state(self, config):
        """`stream_chat_events` reads prior state to decide how much of the
        stored application row to hydrate (SDD 11 §3).
        """
        return self._state


async def _collect(graph):
    return [event async for event in stream_chat_events(graph, "APP-1", "customer", "oi")]


async def test_updates_become_started_and_finished_trace_events():
    graph = _FakeGraph([("updates", {"router": {}})])

    events = await _collect(graph)

    started = json.loads(events[0].split("data: ", 1)[1])
    finished = json.loads(events[1].split("data: ", 1)[1])

    assert started["node"] == "router"
    assert started["status"] == "started"
    assert started["turn_id"].startswith("chat-")
    assert started["turn_seq"] == 0
    assert finished["node"] == "router"
    assert finished["status"] == "finished"
    assert finished["turn_id"] == started["turn_id"]
    assert finished["turn_seq"] == 1


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


async def test_intake_structured_output_is_not_streamed_to_the_customer():
    """`intake` calls `with_structured_output`, so its "tokens" are the JSON of
    `_ExtractedFields`. Forwarding them puts `{"asset_value":400000.0,...}` in
    the customer's chat window before the answer.
    """
    graph = _FakeGraph(
        [
            ("messages", (AIMessageChunk(content='{"asset'), {"langgraph_node": "intake"})),
            ("messages", (AIMessageChunk(content='_value":'), {"langgraph_node": "intake"})),
            ("messages", (AIMessageChunk(content="Olá!"), {"langgraph_node": "customer_response"})),
        ]
    )

    events = await _collect(graph)
    tokens = [e for e in events if e.startswith("event: token\n")]

    assert tokens == ['event: token\ndata: {"text": "Olá!"}\n\n']


async def test_the_finished_message_does_not_repeat_the_streamed_answer():
    """`stream_mode="messages"` yields both the `AIMessageChunk`s the LLM emits
    and the finished `AIMessage` the node writes into `messages`. Forwarding
    both sends the answer twice — once token by token, then once entire.
    """
    graph = _FakeGraph(
        [
            ("messages", (AIMessageChunk(content="Parcela "), {"langgraph_node": "customer_response"})),
            ("messages", (AIMessageChunk(content="de R$ 2.658,78."), {"langgraph_node": "customer_response"})),
            ("messages", (AIMessage(content="Parcela de R$ 2.658,78."), {"langgraph_node": "customer_response"})),
        ]
    )

    events = await _collect(graph)
    streamed = "".join(json.loads(e.split("data: ", 1)[1])["text"] for e in events if e.startswith("event: token\n"))

    assert streamed == "Parcela de R$ 2.658,78."


async def test_state_fires_once_immediately_before_done():
    graph = _FakeGraph(
        [("updates", {"decision": {"stage": "review", "calc": None, "decision": None}})]
    )

    events = await _collect(graph)

    assert events[-2].startswith("event: state\n")
    assert events[-1] == 'event: done\ndata: {"thread_id": "APP-1"}\n\n'
    assert sum(1 for e in events if e.startswith("event: state\n")) == 1


async def test_approval_stream_exposes_real_persistence_milestones():
    graph = _FakeGraph(
        [
            ("custom", {"trace_event": {"node": "persist_decision", "status": "started"}}),
            (
                "custom",
                {
                    "trace_event": {
                        "node": "persist_decision",
                        "status": "step",
                        "step": "precedent_upsert",
                        "detail": {"collection": "historical_cases"},
                    }
                },
            ),
            ("updates", {"persist_decision": {}}),
        ],
        state={"decision": {"outcome": "approved"}, "stage": "done"},
    )

    events = [event async for event in stream_approval_events(graph, "APP-1", {"outcome": "approved"})]
    traces = [json.loads(event.split("data: ", 1)[1]) for event in events if event.startswith("event: trace\n")]

    assert [(event["status"], event.get("step")) for event in traces] == [
        ("started", None),
        ("step", "precedent_upsert"),
        ("finished", None),
    ]
    assert all(event["source"] == "approval" for event in traces)
    assert traces[1]["detail"]["collection"] == "historical_cases"
    assert events[-2].startswith("event: state\n")
    assert events[-1] == 'event: done\ndata: {"thread_id": "APP-1"}\n\n'
