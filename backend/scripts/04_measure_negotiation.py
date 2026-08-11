"""SDD 06 §6 — measure the negotiation turn latency, for real.

Deep Agents means more LLM calls per turn: the main loop, plus one round trip
per subagent delegation. SDD 06 sets the budget at a **median of 15 s per
turn**; above it, the mitigations in §6 apply, and the `AGENT_MODE=react`
fallback exists for the case where they are not enough.

Fifteen seconds of silence in front of a panel is very long, so this also
reports **time to first token** — the number that decides whether the wait is
tolerable, because a wait you can watch is not the same as a wait you cannot.

It drives `stream_chat_events` itself, not the graph directly, so what is timed
is the path `/api/chat` actually runs. Re-run it on the day: the numbers move
with the model and with the venue's network.

    uv run python scripts/04_measure_negotiation.py
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import get_db  # noqa: E402
from app.graph.builder import build_graph  # noqa: E402
from app.main import stream_chat_events  # noqa: E402
from app.memory.checkpointer import get_checkpointer  # noqa: E402
from app.memory.store import get_store  # noqa: E402

THREAD = "APP-MEASURE-0001"
CUSTOMER = "CUST-0001"

# Beat 6 of the demo plan: three structures in sequence, ending on Open Finance
# because that one moves the case for a business reason rather than a numeric one.
TURNS: list[tuple[str, str]] = [
    ("customer", "Quero financiar um apartamento de R$ 400 mil, com R$ 100 mil de entrada, em 360 meses."),
    ("analyst", "Abri o caso. Qual a situação e o que dizem os precedentes?"),
    ("analyst", "Por que exatamente ele não passou no automático?"),
    ("analyst", "E se a entrada subisse para R$ 168 mil?"),
    ("analyst", "E se, além disso, o prazo fosse para 420 meses?"),
    ("analyst", "A cliente tem ativos que possa compartilhar via Open Finance?"),
    ("analyst", "Pode aprovar com condições."),
]


def _reset() -> None:
    db = get_db()
    db["applications"].delete_one({"_id": THREAD})
    db["decisions_log"].delete_many({"application_id": THREAD})
    db["historical_cases"].delete_one({"_id": f"CASE-{THREAD.removeprefix('APP-')}"})
    for collection in ("checkpoints", "checkpoint_writes"):
        db[collection].delete_many({"thread_id": THREAD})

    now = datetime.now(timezone.utc)
    db["applications"].insert_one(
        {
            "_id": THREAD,
            "thread_id": THREAD,
            "customer_id": CUSTOMER,
            "product": "mortgage",
            "asset_value": 400_000.0,
            "down_payment": 100_000.0,
            "requested_amount": 300_000.0,
            "term_months": 360,
            "purpose": "Aquisição de imóvel residencial próprio",
            "status": "draft",
            "created_at": now,
            "updated_at": now,
            "latest_assessment": None,
        }
    )


async def _run_turn(graph, persona: str, message: str) -> dict:
    started = time.perf_counter()
    first_token: float | None = None
    answer: list[str] = []
    nodes: list[str] = []
    steps: list[str] = []
    final_state: dict = {}

    async for raw in stream_chat_events(graph, THREAD, persona, message):
        event, _, payload = raw.partition("\n")
        name = event.removeprefix("event: ")
        data = json.loads(payload.removeprefix("data: ").strip())

        if name == "token":
            first_token = first_token or time.perf_counter() - started
            answer.append(data["text"])
        elif name == "trace":
            if data.get("status") == "step":
                steps.append(f"{data['step']}")
            elif data.get("status") == "finished":
                nodes.append(f"{data['node']}({data['ms']}ms)")
            elif data.get("status") == "interrupted":
                nodes.append("await_approval(INTERRUPTED)")
        elif name == "state":
            final_state = data

    return {
        "seconds": time.perf_counter() - started,
        "first_token": first_token,
        "answer": "".join(answer),
        "nodes": nodes,
        "steps": steps,
        "state": final_state,
    }


async def main(keep: bool) -> int:
    _reset()
    graph = build_graph(checkpointer=get_checkpointer(), store=get_store())
    results = []

    for persona, message in TURNS:
        print(f"\n{'=' * 78}\n[{persona}] {message}\n{'-' * 78}")
        result = await _run_turn(graph, persona, message)
        results.append((persona, result))

        print(f"  nós   : {' -> '.join(result['nodes'])}")
        if result["steps"]:
            print(f"  passos: {' -> '.join(result['steps'])}")
        ttft = f"{result['first_token']:.1f}s" if result["first_token"] else "—"
        print(f"  tempo : {result['seconds']:.1f}s  (primeiro token: {ttft})")
        print(f"\n{result['answer']}\n")

    negotiation_turns = [
        r["seconds"] for persona, r in results if persona == "analyst" and r["steps"]
    ]
    analyst_turns = [r["seconds"] for persona, r in results if persona == "analyst"]

    print(f"\n{'=' * 78}\nSDD 06 §6 — orçamento: mediana de 15 s por turno")
    print(f"  turnos do analista      : {len(analyst_turns)}")
    print(f"  mediana (todos)         : {statistics.median(analyst_turns):.1f}s")
    if negotiation_turns:
        print(f"  mediana (com ferramenta): {statistics.median(negotiation_turns):.1f}s")
        print(f"  pior caso               : {max(analyst_turns):.1f}s")
    first_tokens = [r["first_token"] for _p, r in results if r["first_token"]]
    if first_tokens:
        print(f"  mediana do 1º token     : {statistics.median(first_tokens):.1f}s")

    within_budget = statistics.median(analyst_turns) <= 15
    print(f"\n  {'OK' if within_budget else 'ACIMA DO ORÇAMENTO — aplicar SDD 06 §6'}")

    pending = (results[-1][1]["state"] or {}).get("pending_approval")
    print(f"  pending_approval no fim : {'sim' if pending else 'não'}")

    if not keep:
        _reset()
        get_db()["applications"].delete_one({"_id": THREAD})
    return 0 if within_budget else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true", help="leave the thread in Atlas")
    raise SystemExit(asyncio.run(main(parser.parse_args().keep)))
