# SDD 07 — Memory

> Part of the [FSI Credit Assistant SDD](00-overview.md) · Satisfies **R2** and **R3**
> **Reads:** [04 Graph state](04-graph-state.md), [03 Indexes](03-atlas-indexes.md)
> **Feeds:** [05 Nodes](05-graph-nodes-and-routing.md), [16 Demo plan](16-demo-plan.md)
> **Implemented by:** `backend/app/memory/checkpointer.py`, `backend/app/memory/store.py`
> **Model:** Sonnet — but read [13](13-verified-api-contract.md) first, this is where stale
> documentation will bite hardest.

---

## 0. The distinction that must land on stage

Short-term and long-term memory are **different mechanisms**, not the same store with
different TTLs. Conflating them is the most common architectural mistake in agent systems,
and the panel will be listening for whether you understand the difference.

| | Short-term | Long-term |
|---|---|---|
| What | Serialised graph state per superstep | Structured knowledge about people |
| Shape | Opaque blob, library-managed | Queryable documents, app-defined |
| Lifetime | TTL 24h | Permanent |
| Mechanism | `MongoDBSaver` (checkpointer) | `MongoDBStore` (`BaseStore`) |
| Purpose | Resume, replay, time-travel, durability | Personalisation, calibration, eligibility facts |
| Read by | LangGraph itself, transparently | `load_context` node, explicitly |

Both are **official MongoDB-maintained integrations**. You did not improvise memory; you
used the first-class implementations of LangGraph's two canonical persistence interfaces.

---

## 1. Short-term memory

```python
from pymongo import MongoClient
from langgraph.checkpoint.mongodb import MongoDBSaver

client = MongoClient(settings.mongodb_uri)
checkpointer = MongoDBSaver(
    client,
    db_name="credit_assistant",
    checkpoint_collection_name="checkpoints",
    writes_collection_name="checkpoint_writes",
    ttl=86400,
)
```

> ### ⚠️ Do not import `AsyncMongoDBSaver`
>
> It does not exist in `langgraph-checkpoint-mongodb` 0.4.0.
> `langgraph.checkpoint.mongodb.aio` raises `ModuleNotFoundError`. The module exports
> exactly `['MongoDBSaver', 'saver', 'utils']`.
>
> `MongoDBSaver` already implements the async protocol methods (`aget_tuple`, `alist`,
> `aput`, `aput_writes`) and works correctly with `graph.ainvoke()` / `graph.astream()`.
>
> Verified by introspecting the installed package. The readthedocs page describing
> `AsyncMongoDBSaver` is stale.

### TTL — unverified behaviour

Whether `ttl=86400` creates a native MongoDB TTL index or applies client-side expiry is
**not confirmed**. `scripts/00_check_atlas.py` prints `db.checkpoints.index_information()`
after the first write to settle it ([03 §3](03-atlas-indexes.md)).

Do not describe TTL behaviour on stage before reading that output. "It expires after 24
hours via a TTL index" is a claim an interviewer can check in the Atlas UI in ten seconds.

---

## 2. Long-term memory

Three namespaces, matching the three memory types this demo commits to:

| Namespace | Contents | Written by |
|---|---|---|
| `("customer", customer_id, "preferences")` | *"Prioriza parcela menor sobre prazo curto"*; *"resistente a usar FGTS"* | extraction step in `customer_response`, and `persist_decision` |
| `("customer", customer_id, "facts")` | *"Autônomo, renda comprovada por DECORE"*; *"imóvel em inventário — bloqueio jurídico"* | `intake` / `negotiation` when a hard fact surfaces |
| `("analyst", analyst_id, "decision_patterns")` | *"Carlos aceita DTI até 33% quando há ativos compartilhados via Open Finance"* | `persist_decision`, derived from approved scenarios |

```python
from langgraph.store.mongodb import MongoDBStore, create_vector_index_config

index_config = create_vector_index_config(
    dims=1024,
    embed=get_embeddings(),          # factory — see [08 §1](08-retrieval.md)
    fields=["content"],
    relevance_score_fn="cosine",
)

store = MongoDBStore.from_conn_string(
    conn_string=settings.mongodb_uri,
    db_name="credit_assistant",
    collection_name="agent_memories",
    index_config=index_config,
)
```

Note `db_name` defaults to `"checkpointing_db"` — **always pass it explicitly**, or long-term
memory silently lands in a different database from everything else.

### Value shape

```python
store.put(
    ("analyst", "ANALYST-CARLOS", "decision_patterns"),
    key="dti-tolerance-with-open-finance",
    value={
        "content": "Carlos aprova DTI até 33% quando há ativos compartilhados via Open Finance com liquidez D+1.",
        "evidence_application_ids": ["APP-20260814-0001"],
        "observed_at": "2026-08-14T13:07:00Z",
    },
)
```

`content` is the field named in `fields=[...]`, so it is the embedded one. Keys are stable
slugs, not hashes — the demo needs to update an existing memory, not accumulate near
duplicates.

> `MongoDBStore` 0.3.0 has **no** `rerank_config` parameter, contrary to some documentation.
> Constructor params are `(collection, ttl_config, index_config, auto_index_timeout,
> query_model, **kwargs)`. See [13 §3](13-verified-api-contract.md).

### If the M0 index limit forces it

All three namespaces are read by exact key from `load_context`. Semantic search over
memories is not required by any demo beat. Dropping `index_config` costs nothing narratively
— see the fallback in [03 §3](03-atlas-indexes.md).

---

## 3. The durability demo beat

Mid-negotiation: kill the backend process (`Ctrl+C`), restart it, send the next message. The
conversation continues with full context, because state lives in `checkpoints` on Atlas.

Twenty seconds, and it proves the architecture better than any slide. Beat 7 in
[16](16-demo-plan.md).

**Precondition:** the FastAPI process holds no conversational state in memory. Every request
reconstructs from the checkpointer; the graph is built once per process, never per session.
See [04 §4](04-graph-state.md).

**Rehearse this specifically.** It is the beat most likely to expose an accidental in-memory
cache, and finding that out on Friday is not the plan.

---

## Acceptance criteria

- [ ] No import of `AsyncMongoDBSaver` anywhere in the codebase.
- [ ] `MongoDBStore` is constructed with an explicit `db_name="credit_assistant"`.
- [ ] Killing and restarting the API mid-thread preserves the conversation — verified
      manually at least twice.
- [ ] All three namespaces are written at least once during a full demo run.
- [ ] `load_context` reads all three and surfaces them in the trace panel as a memory-read
      step.
- [ ] `db.checkpoints.index_information()` output is recorded, and the TTL claim used on
      stage matches it.
