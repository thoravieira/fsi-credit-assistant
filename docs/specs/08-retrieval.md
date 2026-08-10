# SDD 08 — Retrieval

> Part of the [FSI Credit Assistant SDD](00-overview.md) · Satisfies **R5**
> **Reads:** [02 Data model](02-data-model.md), [03 Indexes](03-atlas-indexes.md)
> **Feeds:** [05 Nodes](05-graph-nodes-and-routing.md), [06 Negotiation](06-negotiation-agent.md), [09 Eval](09-retrieval-eval.md)
> **Implemented by:** `backend/app/embeddings.py`, `backend/app/retrieval/{policies,precedents}.py`
> **Model:** Sonnet

---

## 1. Embeddings

`voyage-4-lite`, 1024 dimensions, via `langchain-voyageai`.

Voyage AI is a MongoDB company and the officially recommended embedding provider for Atlas
Vector Search — a deliberate, defensible choice in front of this audience. Free tier is
200M tokens; the entire dataset costs roughly 50k.

`backend/app/embeddings.py` is a factory keyed on `EMBEDDING_PROVIDER`:

```python
def get_embeddings() -> Embeddings:
    if settings.embedding_provider == "voyage":
        from langchain_voyageai import VoyageAIEmbeddings
        return VoyageAIEmbeddings(model="voyage-4-lite", output_dimension=1024)
    from langchain_openai import OpenAIEmbeddings
    return OpenAIEmbeddings(model="text-embedding-3-small", dimensions=1024)
```

Both providers are pinned to **1024 dimensions** so the vector index definition is
provider-agnostic. `text-embedding-3-small` truncates via `dimensions`; `voyage-4-lite` via
`output_dimension`. Both parameters verified present in the installed packages
([13 §6](13-verified-api-contract.md)).

> Switching providers still requires **re-embedding** the corpus
> (`scripts/02_seed.py --reembed`) — the vectors are not interchangeable. Only the index
> *schema* is stable. This is the escape hatch for risk 7 in
> [15](15-risks-and-open-items.md).

---

## 2. What gets embedded, and why it matters

**Policies:** the `text` field — full prose policy language.
**Cases:** the `summary` field — a narrative paragraph, never a serialisation of the
structured fields.

This is a deliberate technical position, worth articulating out loud.

Cosine similarity between `{"ltv": 0.80}` and `{"ltv": 0.75}` is noise. Numeric fields carry
no semantic signal in embedding space — the tokeniser sees digits, and near-identical
numbers can land far apart while unrelated ones land close. What *does* carry signal is
*"autônomo com LTV alto, compensado por relacionamento longo e ativos compartilhados via
Open Finance"*.

Therefore:

| Kind of information | Goes to | Serves |
|---|---|---|
| Prose, narrative, rationale | The vector index (`embedding`) | Semantics — "cases like this one" |
| Numbers, categories, status | `filter` fields on the index | Exact constraints, pre-filtered at query time |

### Why pre-filtering is the point

Atlas applies `filter` fields **during** the ANN traversal, not afterwards. With
post-filtering, `k=3` can return three results that all get discarded by the filter, leaving
you with nothing. With pre-filtering, `k=3` returns three *eligible* results.

This is what makes the prose/numbers split work without destroying recall, and it is a
genuine Atlas capability worth naming on stage rather than assuming the panel infers it.

---

## 3. Query construction

`policy_retrieval` builds its query from the **application**, not from the user's raw text.
Raw user text is noisy and often does not contain the terms the policy corpus uses.

```python
query = (f"{product} com LTV de {ltv:.0%}, prazo de {term_months} meses, "
         f"comprometimento de renda de {dti:.0%}, cliente {employment_type}")
docs = vector_store.similarity_search(query, k=4, pre_filter={"product": product})
```

> The parameter is **`pre_filter`**, not `filter`. Verified signature in
> [13 §4](13-verified-api-contract.md). This is a likely hallucination point.

`precedent_search` builds a natural-language description of the case and filters by
`product`, optionally by `ltv_band`.

Both nodes emit the query, the matched IDs and the scores as a `custom` stream event so the
trace panel can show them ([11 §2](11-api-sse.md)).

---

## 4. The precedent loop

`persist_decision` writes the just-decided case into `historical_cases` **with a freshly
generated embedding**, making it immediately retrievable by the next query.

The system improves without retraining anything. This turns the demo from "RAG over a static
dataset" into a system that learns from operation — and it is the difference between a
feature and an architecture.

**It is demonstrable live** (beat 8 in [16](16-demo-plan.md)): decide a case, then run a
similar simulation and watch the new case appear in `precedent_search` results in the trace
panel. Rehearse the pair of inputs that makes this work — a near-miss similarity is not
convincing on a projector.

---

## Acceptance criteria

- [ ] `get_embeddings()` returns 1024-dimensional vectors for both providers.
- [ ] Switching `EMBEDDING_PROVIDER` and running `02_seed.py --reembed` produces a working
      system with no index changes.
- [ ] `policy_retrieval` uses `pre_filter`, never post-filtering.
- [ ] A policy query for a mortgage never returns an auto-loan policy.
- [ ] `persist_decision` writes a case with a populated `embedding` array of length 1024.
- [ ] The just-persisted case is retrievable by a similar query within the same session.
- [ ] `recall@3 ≥ 0.8` on the golden set — see [09](09-retrieval-eval.md).
