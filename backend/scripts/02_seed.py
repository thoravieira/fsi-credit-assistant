"""SDD 02 + 08 — seed customer_profiles, credit_policies, historical_cases,
applications and decisions_log.

Idempotent: upserts by `_id`, so re-running leaves the same document count.
Embeddings are only recomputed when the source text changed or --reembed is
passed, to avoid needless embedding-API calls on every re-run.

`applications`/`decisions_log` are seeded from `data/applications/applications_seed.json`
using the exact production domain code (`compute_scenario`, `evaluate`, `append_event`) —
no reimplementation, no LLM, no invented numbers. See `seed_applications` below.

--reset wipes every collection that holds nothing but reproducible fixtures or
live-demo-day data (which by definition doesn't exist before the demo), then runs
the normal seed flow — a full, reproducible rebuild. See `reset_demo_data` below.
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml
from pymongo import ReplaceOne

from app.audit import append_event
from app.config import DEMO_ANALYST_ID, get_settings
from app.db import get_client
from app.domain.calculator import compute_scenario
from app.domain.rules import evaluate
from app.embeddings import get_embeddings

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"

# APP-SEED-NNNN, never APP-YYYYMMDD-NNNN — that live-application format is
# reserved for real applications created through the API on demo day, and
# must never collide with these seed records.
SEED_APPLICATION_IDS = [f"APP-SEED-{i:04d}" for i in range(1, 51)]

# Collections that hold nothing but reproducible fixtures or live-demo-day
# data (which doesn't exist yet before the demo) — safe to wipe unconditionally
# under --reset. `historical_cases` is handled separately: only the
# agent-derived precedent cases (written live by `persist_decision.py`, tagged
# with `source_application_id`) are removed, leaving the ~60 authored seed
# cases from `data/cases/cases.json` untouched.
RESET_WIPE_COLLECTIONS = [
    "applications",
    "decisions_log",
    "checkpoints",
    "checkpoint_writes",
    "trace_log",
    "agent_memories",
]


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def load_policies() -> list[dict]:
    docs = []
    for path in sorted((DATA_DIR / "policies").glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        _, frontmatter, body = raw.split("---", 2)
        doc = yaml.safe_load(frontmatter)
        doc["text"] = body.strip()
        docs.append(doc)
    return docs


def load_cases() -> list[dict]:
    return json.loads((DATA_DIR / "cases" / "cases.json").read_text(encoding="utf-8"))


def load_profiles() -> list[dict]:
    return json.loads((DATA_DIR / "profiles" / "profiles.json").read_text(encoding="utf-8"))


def load_applications() -> list[dict]:
    return json.loads(
        (DATA_DIR / "applications" / "applications_seed.json").read_text(encoding="utf-8")
    )


def seed_embedded_collection(
    coll, docs: list[dict], text_field: str, embeddings, reembed: bool
) -> None:
    existing_meta = {
        d["_id"]: (d.get("_content_hash"), d.get("embedding"))
        for d in coll.find({}, {"_content_hash": 1, "embedding": 1})
    }

    to_embed = []
    for i, doc in enumerate(docs):
        h = content_hash(doc[text_field])
        old_hash, old_embedding = existing_meta.get(doc["_id"], (None, None))
        doc["_content_hash"] = h
        if reembed or old_hash != h or not old_embedding:
            to_embed.append(i)
        else:
            doc["embedding"] = old_embedding

    if to_embed:
        texts = [docs[i][text_field] for i in to_embed]
        vectors = embeddings.embed_documents(texts)
        for i, vector in zip(to_embed, vectors):
            docs[i]["embedding"] = vector

    ops = [ReplaceOne({"_id": doc["_id"]}, doc, upsert=True) for doc in docs]
    result = coll.bulk_write(ops)
    print(
        f"  {coll.name}: {len(docs)} docs upserted "
        f"(matched={result.matched_count}, upserted={len(result.upserted_ids or {})}, "
        f"embedded={len(to_embed)}, reused={len(docs) - len(to_embed)})"
    )


def seed_profiles(coll, docs: list[dict]) -> None:
    ops = [ReplaceOne({"_id": doc["_id"]}, doc, upsert=True) for doc in docs]
    result = coll.bulk_write(ops)
    print(
        f"  {coll.name}: {len(docs)} docs upserted "
        f"(matched={result.matched_count}, upserted={len(result.upserted_ids or {})})"
    )


def seed_applications(db, profiles_by_id: dict[str, dict]) -> None:
    """Seed ~50 `applications` + their `decisions_log` events from
    `data/applications/applications_seed.json`.

    Every `calc`/`decision` is produced by the real `compute_scenario` /
    `evaluate` domain functions run against the real seeded profile — the
    same functions the graph itself calls (`decision.py`, `scenario.py`).
    `status` is always `result["outcome"]`; nothing here fakes an outcome
    independent of what the domain code actually returns.

    Idempotent: `applications` upserts by `_id`; `decisions_log` is cleared
    for these seed application ids first, then re-appended fresh, so
    re-running never accumulates duplicate log entries.
    """
    specs = load_applications()

    db["decisions_log"].delete_many({"application_id": {"$in": SEED_APPLICATION_IDS}})

    ops = []
    resolved_count = 0
    for spec in specs:
        application_id = spec["_id"]
        profile = profiles_by_id[spec["customer_id"]]
        product = spec["product"]
        asset_value = spec["asset_value"]
        down_payment = spec["down_payment"]
        term_months = spec["term_months"]
        financed = asset_value - down_payment

        calc = compute_scenario(
            product=product,
            asset_value=asset_value,
            financed=financed,
            term_months=term_months,
            net_income=profile["income"]["net_monthly"],
            existing_debt=profile["credit"]["existing_monthly_debt"],
            score=profile["credit"]["internal_score"],
        )
        application = {
            "product": product,
            "requested_amount": financed,
            "term_months": term_months,
        }
        decision = evaluate(application, calc, profile)

        doc = {
            "_id": application_id,
            "thread_id": application_id,
            "customer_id": spec["customer_id"],
            "product": product,
            "asset_value": asset_value,
            "down_payment": down_payment,
            "requested_amount": financed,
            "term_months": term_months,
            "purpose": spec["purpose"],
            "status": decision["outcome"],
            "created_at": datetime.fromisoformat(spec["created_at"]),
            "updated_at": datetime.fromisoformat(spec["updated_at"]),
            "latest_assessment": {"calc": calc, "decision": decision},
        }

        # Mirrors `decision.py`'s `assessment` event exactly — written on
        # every path, including automatic approvals (SDD 02 §6).
        append_event(
            application_id,
            "assessment",
            {"type": "agent", "id": "system"},
            calc=calc,
            outcome=decision["outcome"],
            policy_refs=decision["policy_refs"],
            rationale=" ".join(decision["reasons"]),
        )

        resolution = spec.get("resolution")
        if resolution is not None:
            # Mirrors `persist_decision.py`'s `final_decision` event and
            # `applications` update, minus the precedent/memory writes (out
            # of scope for a seed script — those are agent-derived).
            append_event(
                application_id,
                "final_decision",
                {"type": "analyst", "id": DEMO_ANALYST_ID},
                calc=calc,
                outcome=resolution["outcome"],
                policy_refs=resolution["policy_refs"],
                precedent_refs=[],
                conditions=resolution["conditions"],
                rationale=resolution["rationale"],
            )
            doc["status"] = resolution["outcome"]
            doc["final_decision"] = {
                "outcome": resolution["outcome"],
                "policy_refs": resolution["policy_refs"],
                "rationale": resolution["rationale"],
                "conditions": resolution["conditions"],
                "precedent_refs": [],
            }
            resolved_count += 1

        ops.append(ReplaceOne({"_id": application_id}, doc, upsert=True))

    result = db["applications"].bulk_write(ops)
    print(
        f"  applications: {len(specs)} docs upserted "
        f"(matched={result.matched_count}, upserted={len(result.upserted_ids or {})}), "
        f"{resolved_count} resolved by analyst, {len(specs) - resolved_count} open/closed by system"
    )


def reset_demo_data(db) -> None:
    """--reset: unconditional wipe of every collection that holds nothing but
    reproducible fixtures or live-demo-day data, so the normal seed flow that
    follows produces a fully reproducible pristine baseline.
    """
    print("## Resetting demo data")
    for name in RESET_WIPE_COLLECTIONS:
        result = db[name].delete_many({})
        print(f"  {name}: deleted {result.deleted_count}")

    # Only the agent-derived precedent cases written live by
    # `persist_decision.py` (tagged with `source_application_id`) — the ~60
    # authored seed cases from `data/cases/cases.json` are left untouched.
    result = db["historical_cases"].delete_many({"source_application_id": {"$exists": True}})
    print(f"  historical_cases (agent-derived precedents only): deleted {result.deleted_count}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reembed", action="store_true", help="Force re-embedding of all policies and cases."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help=(
            "Wipe applications, decisions_log, checkpoints, checkpoint_writes, "
            "trace_log, agent_memories, and agent-derived historical_cases before "
            "seeding, for a fully reproducible pristine baseline."
        ),
    )
    args = parser.parse_args()

    settings = get_settings()
    client = get_client()
    db = client[settings.mongodb_db]
    embeddings = get_embeddings()

    if args.reset:
        reset_demo_data(db)

    print("## Seeding customer_profiles")
    profiles = load_profiles()
    seed_profiles(db["customer_profiles"], profiles)

    print("## Seeding credit_policies")
    seed_embedded_collection(
        db["credit_policies"], load_policies(), "text", embeddings, args.reembed
    )

    print("## Seeding historical_cases")
    seed_embedded_collection(
        db["historical_cases"], load_cases(), "summary", embeddings, args.reembed
    )

    print("## Seeding applications + decisions_log")
    profiles_by_id = {p["_id"]: p for p in profiles}
    seed_applications(db, profiles_by_id)

    print()
    print("Done.")


if __name__ == "__main__":
    main()
