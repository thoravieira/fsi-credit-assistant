"""SDD 04 §2 acceptance: AgentState has exactly two reducer fields."""

import operator
from typing import Annotated, get_args, get_origin, get_type_hints

from langgraph.graph.message import add_messages

from app.graph.state import AgentState


def test_exactly_two_reducer_fields():
    hints = get_type_hints(AgentState, include_extras=True)

    reducers = {}
    for field, hint in hints.items():
        if get_origin(hint) is Annotated:
            _, *metadata = get_args(hint)
            if metadata:
                reducers[field] = metadata[0]

    assert set(reducers) == {"messages", "scenarios"}
    assert reducers["messages"] is add_messages
    assert reducers["scenarios"] is operator.add
