# SDD 09 — Retrieval evaluation

> Part of the [FSI Credit Assistant SDD](00-overview.md)
> **Reads:** [08 Retrieval](08-retrieval.md), [02 Data model](02-data-model.md)
> **Implemented by:** `backend/scripts/03_eval_retrieval.py`
> **Model:** Sonnet
> **Effort:** ~1 hour. Disproportionate return on interview score.

---

## 1. Purpose

When the panel asks *"how do you know the retrieval isn't hallucinating?"*, the answer
should be **a number you measured**, not an opinion you hold.

Almost no candidate does this. It is the cheapest available differentiator in the entire
build.

---

## 2. Design

A golden set of 10 queries, each mapped to the policy IDs that *should* be retrieved.

```python
GOLDEN_SET = [
    {
        "query": "financiamento imobiliário com entrada de 20% e prazo de 30 anos",
        "product": "mortgage",
        "expected": ["POL-014", "POL-021"],
    },
    {
        "query": "cliente autônomo sem holerite, como comprovar renda",
        "product": "mortgage",
        "expected": ["POL-007"],
    },
    # ... 8 more
]
```

Cover every policy family from [02 §3](02-data-model.md) at least once. Include at least two
queries phrased the way a *customer* would speak, not the way the policy is written — that
is the case where lexical search fails and vector search earns its place.

Report:

| Metric | Definition | Healthy |
|---|---|---|
| `recall@3` | Fraction of queries where at least one expected ID is in the top 3 | ≥ 0.8 |
| `recall@5` | Same at k=5 | ≥ 0.9 |
| mean top-1 score | Average cosine score of the best hit | report, no threshold |
| worst query | The query with the lowest score | inspect manually |

Write the output to `docs/retrieval-eval.md` and commit it. A committed measurement is
evidence; a number recited from memory is a claim.

---

## 3. What to do if it fails

If `recall@3 < 0.8`, the fix is **chunking, not prompting**. In order of likely payoff:

1. **Chunks too long or too short.** Target 80–200 words, one rule per chunk. A chunk
   covering three unrelated rules dilutes its own embedding.
2. **Chunk missing its own context.** Each chunk must name its product and rule type in the
   prose. "O limite é de 80%" embeds badly; "O limite de LTV para financiamento imobiliário
   residencial é de 80%" embeds well.
3. **Query construction wrong.** See [08 §3](08-retrieval.md) — build the query from the
   application, not from raw user text.
4. **Only then** consider hybrid search (`MongoDBAtlasHybridSearchRetriever` exists and is
   listed in [13 §4](13-verified-api-contract.md)) — but it costs an additional full-text
   index, which the M0 index budget may not permit ([03 §3](03-atlas-indexes.md)).

Note the ordering. Reaching for a fancier retriever before fixing the corpus is the classic
RAG mistake, and saying so on stage demonstrates judgement.

---

## Acceptance criteria

- [ ] `scripts/03_eval_retrieval.py` runs standalone and prints the metrics table.
- [ ] Golden set has 10 queries covering every policy family.
- [ ] At least 2 queries are phrased in customer language, not policy language.
- [ ] `recall@3 ≥ 0.8` achieved and the output committed to `docs/retrieval-eval.md`.
- [ ] The number is memorised for beat 10 of the demo.
