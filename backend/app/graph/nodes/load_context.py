"""SDD 05 §1 — load_context node. Reads `customer_profiles` and the two
customer `MongoDBStore` namespaces into state (SDD 07 §2). The analyst
namespace is read by the analyst path, not built in this session.
"""

from langgraph.config import get_stream_writer

from app.db import get_db
from app.graph.state import AgentState
from app.memory.store import customer_facts_namespace, customer_preferences_namespace, get_store
from app.runtime_trace import trace_started


def load_context(state: AgentState) -> dict:
    trace_started("load_context")
    application = state.get("application") or {}
    customer_id = application.get("customer_id")

    profile = None
    memories: list[dict] = []

    if customer_id:
        profile = get_db()["customer_profiles"].find_one({"_id": customer_id})

        store = get_store()
        for item in store.search(customer_preferences_namespace(customer_id)):
            memories.append({"namespace": "preferences", "key": item.key, **item.value})
        for item in store.search(customer_facts_namespace(customer_id)):
            memories.append({"namespace": "facts", "key": item.key, **item.value})

    writer = get_stream_writer()
    writer(
        {
            "op": "load_context",
            "customer_id": customer_id,
            "profile_found": profile is not None,
            "memory_count": len(memories),
        }
    )

    return {"profile": profile, "memories": memories}
