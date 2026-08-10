"""SDD 03 §1-2 — standard + vector search indexes. Idempotent.

`agent_memories` is not created here — it is managed by `MongoDBStore` in a
later session ([13 §3](../../docs/specs/13-verified-api-contract.md)).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pymongo import ASCENDING, DESCENDING

from app.config import get_settings
from app.db import get_client
from app.embeddings import get_embeddings

DIMENSIONS = 1024
VECTOR_INDEX_NAME = "vector_index"


def ensure_standard_indexes(db) -> None:
    print("## Standard indexes")
    db["applications"].create_index([("status", ASCENDING), ("created_at", DESCENDING)])
    print("  applications: {status: 1, created_at: -1}")
    db["decisions_log"].create_index([("application_id", ASCENDING), ("seq", ASCENDING)])
    print("  decisions_log: {application_id: 1, seq: 1}")
    print()


def ensure_vector_index(coll, embeddings, filters: list[str]) -> None:
    from langchain_mongodb import MongoDBAtlasVectorSearch

    store = MongoDBAtlasVectorSearch(
        collection=coll, embedding=embeddings, index_name=VECTOR_INDEX_NAME
    )
    exists = any(idx["name"] == VECTOR_INDEX_NAME for idx in coll.list_search_indexes())

    if exists:
        print(f"  {coll.name}: {VECTOR_INDEX_NAME} already exists — updating definition")
        store.create_vector_search_index(
            dimensions=DIMENSIONS, filters=filters, update=True, wait_until_complete=120
        )
    else:
        print(f"  {coll.name}: creating {VECTOR_INDEX_NAME}")
        store.create_vector_search_index(
            dimensions=DIMENSIONS, filters=filters, wait_until_complete=120
        )
    print(f"  {coll.name}: queryable (filters={filters})")


def main() -> None:
    settings = get_settings()
    client = get_client()
    db = client[settings.mongodb_db]
    embeddings = get_embeddings()

    ensure_standard_indexes(db)

    print("## Vector search indexes")
    ensure_vector_index(db["credit_policies"], embeddings, filters=["product", "policy_type"])
    ensure_vector_index(
        db["historical_cases"], embeddings, filters=["product", "decision", "ltv_band"]
    )
    print()
    print("Done.")


if __name__ == "__main__":
    main()
