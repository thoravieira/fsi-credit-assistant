"""SDD 07 §2 — long-term memory: structured, queryable knowledge about people.

`db_name` defaults to `"checkpointing_db"` on `MongoDBStore` — always pass it
explicitly (SDD 13 §3), or long-term memory silently lands in a different
database from everything else.

Three namespaces, matching the three memory types this demo commits to.
"""

from functools import lru_cache

from langgraph.store.mongodb import MongoDBStore, create_vector_index_config

from app.config import get_settings
from app.db import get_db
from app.embeddings import get_embeddings


def customer_preferences_namespace(customer_id: str) -> tuple[str, str, str]:
    return ("customer", customer_id, "preferences")


def customer_facts_namespace(customer_id: str) -> tuple[str, str, str]:
    return ("customer", customer_id, "facts")


def analyst_decision_patterns_namespace(analyst_id: str) -> tuple[str, str, str]:
    return ("analyst", analyst_id, "decision_patterns")


@lru_cache
def get_store() -> MongoDBStore:
    settings = get_settings()
    index_config = create_vector_index_config(
        dims=settings.embedding_dimensions,
        embed=get_embeddings(),
        fields=["content"],
        relevance_score_fn="cosine",
    )
    return MongoDBStore(get_db()["agent_memories"], index_config=index_config, auto_index_timeout=120)
