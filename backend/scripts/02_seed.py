"""SDD 02 + 08 — seed customer_profiles, credit_policies, historical_cases.

Idempotent: upserts by `_id`, so re-running leaves the same document count.
Embeddings are only recomputed when the source text changed or --reembed is
passed, to avoid needless embedding-API calls on every re-run.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml
from pymongo import ReplaceOne

from app.config import get_settings
from app.db import get_client
from app.embeddings import get_embeddings

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reembed", action="store_true", help="Force re-embedding of all policies and cases."
    )
    args = parser.parse_args()

    settings = get_settings()
    client = get_client()
    db = client[settings.mongodb_db]
    embeddings = get_embeddings()

    print("## Seeding customer_profiles")
    seed_profiles(db["customer_profiles"], load_profiles())

    print("## Seeding credit_policies")
    seed_embedded_collection(
        db["credit_policies"], load_policies(), "text", embeddings, args.reembed
    )

    print("## Seeding historical_cases")
    seed_embedded_collection(
        db["historical_cases"], load_cases(), "summary", embeddings, args.reembed
    )

    print()
    print("Done.")


if __name__ == "__main__":
    main()
