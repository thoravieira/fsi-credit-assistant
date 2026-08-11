"""SDD 04 §3 / 05 — graph-wide invariants.

Two kinds of check live here:

1. The compiled graph driven end to end with a fake LLM (SDD 14 §2 — wiring,
   routing and state transitions, never model output).
2. The SDD 04 §3 stage-transition table itself, asserted statically.

`application` is seeded into the initial payload because nothing in the graph
hydrates it from `thread_id` yet — see the module docstring in
`test_main.py` for where that gap bites over HTTP.
"""

import ast
from pathlib import Path
from unittest.mock import patch

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import HumanMessage

from app.db import get_db
from app.graph.builder import build_graph
from app.graph.nodes.intake import _ExtractedFields
from app.memory.checkpointer import get_checkpointer
from app.memory.store import get_store

APP_DIR = Path(__file__).resolve().parents[1] / "app"
# `negotiation` is a node too, and it lives outside `nodes/` (SDD 06 §2), so the
# invariant has to look there as well or the one node most likely to reach for
# `stage` is the one node the check misses.
NODE_MODULES = sorted(
    path
    for path in [*(APP_DIR / "graph" / "nodes").glob("*.py"), APP_DIR / "agent" / "negotiation.py"]
    if path.stem != "__init__"
)

# SDD 04 §3 — exhaustive. Any node not listed here must not write `stage`.
ALLOWED_STAGE_WRITERS = {"intake", "decision", "analyst_brief", "persist_decision"}


def _returns_stage_key(path: Path) -> bool:
    """True if any string literal `"stage"` appears in the module — a cheap,
    conservative static check: a node that never mentions "stage" cannot be
    writing it to the returned partial-state dict.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return any(
        isinstance(node, ast.Constant) and node.value == "stage" for node in ast.walk(tree)
    )


def test_only_allowed_nodes_mention_stage():
    offenders = [
        path.stem
        for path in NODE_MODULES
        if path.stem not in ALLOWED_STAGE_WRITERS and _returns_stage_key(path)
    ]
    assert offenders == []


# --- end to end ------------------------------------------------------------


class _FakeExtractor:
    """Stands in for the `intake` LLM: `with_structured_output(...).invoke(...)`."""

    def __init__(self, *results):
        self._results = list(results)

    def with_structured_output(self, schema):
        return self

    def invoke(self, messages):
        return self._results.pop(0) if len(self._results) > 1 else self._results[0]


@pytest.fixture(scope="module")
def graph():
    return build_graph(checkpointer=get_checkpointer(), store=get_store())


@pytest.fixture
def thread():
    application_id = "APP-TEST-SMOKE"
    db = get_db()
    db["applications"].insert_one(
        {
            "_id": application_id,
            "thread_id": application_id,
            "customer_id": "CUST-0001",
            "status": "draft",
            "latest_assessment": None,
        }
    )
    yield application_id
    db["applications"].delete_one({"_id": application_id})
    db["decisions_log"].delete_many({"application_id": application_id})
    for collection in ("checkpoints", "checkpoint_writes"):
        db[collection].delete_many({"thread_id": application_id})


def _payload(application_id, text, **application):
    return {
        "persona": "customer",
        "stage": "intake",
        "application": {
            "application_id": application_id,
            "customer_id": "CUST-0001",
            **application,
        },
        "messages": [HumanMessage(text)],
    }


def _run(graph, application_id, payload, extractor, answer="Segue a simulação."):
    """Stream the graph and return (nodes visited, stage writes, final state)."""
    config = {"configurable": {"thread_id": application_id}}
    visited, stages, final = [], [], {}

    with (
        patch("app.graph.nodes.intake._default_llm", return_value=extractor),
        patch(
            "app.graph.nodes.customer_response._default_llm",
            return_value=FakeListChatModel(responses=[answer]),
        ),
    ):
        for chunk in graph.stream(payload, config=config, stream_mode="updates"):
            for node, update in chunk.items():
                visited.append(node)
                if update:
                    final.update(update)
                    if "stage" in update:
                        stages.append(update["stage"])
    return visited, stages, final


def test_customer_path_runs_end_to_end(graph, thread):
    """SDD 04 acceptance — the stage sequence `intake → assessment → review`.

    The thread starts at `intake`; `intake` writes `assessment` and `decision`
    writes `review`. Those are the only two nodes that touch `stage` on this
    path, which is the §3 table made executable.
    """
    extractor = _FakeExtractor(
        _ExtractedFields(
            product="mortgage", asset_value=400_000.0, down_payment=100_000.0, term_months=360
        )
    )
    payload = _payload(thread, "Quero financiar um apartamento de 400 mil com 100 mil de entrada")

    visited, stages, final = _run(graph, thread, payload, extractor)

    assert visited == [
        "router",
        "intake",
        "load_context",
        "policy_retrieval",
        "credit_calculator",
        "decision",
        "customer_response",
    ]
    assert stages == ["assessment", "review"]
    assert final["decision"]["outcome"] == "manual_review"
    assert final["calc"]["ltv"] == pytest.approx(0.75)
    assert final["policies"]


def test_incomplete_intake_asks_instead_of_calculating(graph, thread):
    """SDD 05 acceptance — a message with no amount produces a clarifying
    question, never touches the calculator, and writes no `decisions_log` entry.
    """
    extractor = _FakeExtractor(_ExtractedFields(product="mortgage"))
    payload = _payload(thread, "quero financiar um apartamento")

    visited, stages, final = _run(
        graph, thread, payload, extractor, answer="Qual o valor do imóvel e da entrada?"
    )

    assert visited == ["router", "intake", "customer_response"]
    assert "credit_calculator" not in visited
    assert "decision" not in visited
    assert stages == []
    assert final["messages"][-1].content == "Qual o valor do imóvel e da entrada?"
    assert get_db()["decisions_log"].count_documents({"application_id": thread}) == 0


def test_all_twelve_nodes_are_wired(graph):
    """SDD 05 §1 — the node list, complete. Both personas, no placeholders."""
    nodes = set(graph.get_graph().nodes) - {"__start__", "__end__"}
    assert nodes == {
        # customer path
        "router",
        "intake",
        "load_context",
        "policy_retrieval",
        "credit_calculator",
        "decision",
        "customer_response",
        # analyst path
        "precedent_search",
        "analyst_brief",
        "negotiation",
        "await_approval",
        "persist_decision",
    }


def test_two_turns_on_one_thread_accumulate_messages_and_overwrite_calc(graph, thread):
    """SDD 04 acceptance — `messages` accumulates via `add_messages`, `calc`
    is replaced. This is the checkpointer doing its job: the second turn never
    re-states the product, and `intake` patches the prior application.
    """
    config = {"configurable": {"thread_id": thread}}

    first = _payload(
        thread, "Apartamento de 400 mil, entrada de 180 mil, 360 meses"
    )
    _run(
        graph,
        thread,
        first,
        _FakeExtractor(
            _ExtractedFields(
                product="mortgage", asset_value=400_000.0, down_payment=180_000.0, term_months=360
            )
        ),
    )
    after_first = graph.get_state(config).values

    # Re-simulation: only the entrada changes, and it rides the same thread.
    _run(
        graph,
        thread,
        {"persona": "customer", "messages": [HumanMessage("e se a entrada fosse 100 mil?")]},
        _FakeExtractor(_ExtractedFields(down_payment=100_000.0)),
    )
    after_second = graph.get_state(config).values

    assert len(after_second["messages"]) > len(after_first["messages"])
    assert after_first["decision"]["outcome"] == "auto_approved"
    assert after_second["decision"]["outcome"] == "manual_review"
    assert after_second["calc"]["ltv"] == pytest.approx(0.75)
    assert after_second["application"]["product"] == "mortgage"  # patched, not re-asked
    assert get_db()["decisions_log"].count_documents({"application_id": thread}) == 2
