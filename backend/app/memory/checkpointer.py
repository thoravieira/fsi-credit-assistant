"""SDD 07 §1 — short-term memory: serialised graph state per superstep.

`MongoDBSaver` — never `AsyncMongoDBSaver`, which does not exist in
`langgraph-checkpoint-mongodb` 0.4.0 (SDD 13 §2). It already implements the
async protocol and works with `graph.ainvoke()` / `graph.astream()`.
"""

from functools import lru_cache

from langgraph.checkpoint.mongodb import MongoDBSaver

from app.config import get_settings
from app.db import get_client


@lru_cache
def get_checkpointer() -> MongoDBSaver:
    settings = get_settings()
    return MongoDBSaver(
        get_client(),
        db_name=settings.mongodb_db,
        checkpoint_collection_name="checkpoints",
        writes_collection_name="checkpoint_writes",
        ttl=86400,
    )
