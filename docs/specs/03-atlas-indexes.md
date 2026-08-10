# SDD 03 — Atlas indexes

> Part of the [FSI Credit Assistant SDD](00-overview.md) · Satisfies part of **R5**
> **Reads:** [02 Data model](02-data-model.md) · **Feeds:** [08 Retrieval](08-retrieval.md), [07 Memory](07-memory.md)
> **Implemented by:** `backend/scripts/00_check_atlas.py`, `backend/scripts/01_create_indexes.py`
> **Model:** Sonnet
> **⚠️ This is the Day 1, hour 1 file. Nothing else can be built until §3 passes.**

---

## 1. Standard indexes

```
applications:      { status: 1, created_at: -1 }     # Carlos's queue
decisions_log:     { application_id: 1, seq: 1 }     # audit trail retrieval
customer_profiles: _id is the customer id            # no additional index
```

---

## 2. Vector search indexes

1024 dimensions, `cosine`, created by `scripts/01_create_indexes.py`.

| Collection | Index name | Path | Filter fields |
|---|---|---|---|
| `credit_policies` | `vector_index` | `embedding` | `product`, `policy_type` |
| `historical_cases` | `vector_index` | `embedding` | `product`, `decision`, `ltv_band` |
| `agent_memories` | `vector_index` | `embedding` | managed by `MongoDBStore` |

**Preferred creation path** — use the vector store's own helper, which creates the index
*and* polls until it is queryable:

```python
vector_store.create_vector_search_index(
    dimensions=1024,
    filters=["product", "policy_type"],
    wait_until_complete=120,
)
```

This avoids hand-rolling a `list_search_indexes` readiness loop, whose status field name
(`status` vs `queryable`) differs across documentation versions. Exact signature in
[13 §4](13-verified-api-contract.md); a low-level `SearchIndexModel` fallback is in
[13 §7](13-verified-api-contract.md).

Filter fields are declared on the index, not applied afterwards. See
[08 §2](08-retrieval.md) for why pre-filtering rather than post-filtering is the whole point.

---

## 3. Cluster probe

> **Resolved 2026-08-10: the cluster is a dedicated M10, not M0.** The index-count limit
> that drove this section no longer applies — dedicated tiers do not impose the low search
> index cap that shared tiers do, and all three vector indexes fit comfortably. The two
> fallbacks below are retained as documentation of the reasoning, not as planned work.
>
> M10 also removes the latency concern (risk 2) and gives predictable performance for the
> live demo instead of shared-tier contention. **Confirm the count in the probe anyway** —
> asserting rather than assuming is the point of the script.

`scripts/00_check_atlas.py` still runs before anything else is built, and must report:

1. Connectivity and server version.
2. Whether 3 vector search indexes can coexist on this cluster — create three throwaway
   indexes on scratch collections, confirm all reach `queryable`, then drop them.
3. `db.checkpoints.index_information()` after a first checkpoint write, to determine
   whether `MongoDBSaver(ttl=...)` creates a native MongoDB TTL index or applies
   client-side expiry. **Do not claim TTL behaviour on stage without this output.**
4. Measured p50/p95 latency of a `$vectorSearch` against the seeded corpus.

### Fallback if the limit is 2 *(no longer expected on M10)*

Instantiate `MongoDBStore` **without** `index_config`, making long-term memory pure
key-value. No demo beat requires semantic search over memories — all three namespaces are
looked up by exact key ([07 §2](07-memory.md)). This drops the requirement to 2 vector
indexes with zero narrative loss.

### Fallback if the limit is 1 *(no longer expected on M10)*

Merge `credit_policies` and `historical_cases` into a single `knowledge` collection with a
`kind` discriminator (`"policy"` | `"case"`), one vector index, and `kind` as a filter
field. Policy RAG and precedent search remain two distinct *queries* with different
pre-filters against one index.

This fallback is arguably better engineering, and it makes a stronger technical point about
pre-filtering — but it costs legibility in the Atlas UI during the demo, which is why it is
the second fallback rather than the design. **Do not adopt it pre-emptively.**

---

## Acceptance criteria

- [ ] `scripts/00_check_atlas.py` runs green against the real M10 cluster and prints all four
      reports from §3.
- [ ] The actual index limit is written into [15 — Risks](15-risks-and-open-items.md),
      replacing "unconfirmed".
- [ ] `scripts/01_create_indexes.py` is idempotent — re-running it does not error on
      existing indexes (`update=True` where appropriate).
- [ ] All required indexes reach `queryable` within `wait_until_complete`.
- [ ] Measured `$vectorSearch` p95 is recorded. If > 1.5 s, act on risk 2 in
      [15](15-risks-and-open-items.md) before building further.
