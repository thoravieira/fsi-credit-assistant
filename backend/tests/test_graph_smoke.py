"""SDD 04 §3 / 05 — graph-wide invariants.

Full end-to-end coverage (drive the compiled graph with a fake LLM, assert
the stage sequence `intake → assessment → review`) is blocked on
`graph/builder.py` and `domain/rules.py`, both deferred to the Opus session
— see the canary tests in `test_nodes_customer_path.py` and `test_main.py`.
Per-node behaviour for everything buildable today (router, intake,
load_context, policy_retrieval, credit_calculator, customer_response,
routing functions) is covered in `test_nodes_customer_path.py` and
`test_routing.py`.

This file covers what's independently verifiable without compiling the
graph: the SDD 04 §3 stage-transition table itself.
"""

import ast
from pathlib import Path

NODES_DIR = Path(__file__).resolve().parents[1] / "app" / "graph" / "nodes"

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
        for path in NODES_DIR.glob("*.py")
        if path.stem != "__init__" and path.stem not in ALLOWED_STAGE_WRITERS
        and _returns_stage_key(path)
    ]
    assert offenders == []
