# SDD 14 — Repository layout and testing

> Part of the [FSI Credit Assistant SDD](00-overview.md)
> **Model:** Sonnet

---

## 1. Layout

```
fsi-credit-assistant/
├── README.md                       quickstart, architecture summary, reproduction steps
├── .env.example
├── .gitignore                      .temp/ on line 1
├── docker-compose.yml              atlas-local + api + web
├── Dockerfile.api
├── Dockerfile.web
├── Makefile                        setup · seed · dev · test · eval · demo-reset
├── docs/
│   ├── specs/                      ← this spec set (00–17)
│   ├── architecture.md             reader-facing narrative
│   ├── diagrams/{graph,data-flow,memory}.mmd
│   ├── objection-bank.md
│   ├── demo-script.md
│   ├── slides-outline.md
│   ├── retrieval-eval.md           committed output of 03_eval_retrieval.py
│   └── adr/
│       ├── 0001-mongodb-as-single-data-plane.md
│       ├── 0002-hybrid-deterministic-agentic-graph.md
│       ├── 0003-voyage-ai-embeddings.md
│       └── 0004-prose-embeddings-structured-filters.md
├── backend/
│   ├── pyproject.toml              uv, versions pinned per [13 §1](13-verified-api-contract.md)
│   ├── app/
│   │   ├── main.py                 FastAPI + SSE
│   │   ├── config.py               pydantic-settings
│   │   ├── db.py                   Mongo client singleton
│   │   ├── embeddings.py           provider factory
│   │   ├── graph/
│   │   │   ├── state.py
│   │   │   ├── builder.py                  [OPUS]
│   │   │   ├── nodes/*.py                  negotiation.py [OPUS]
│   │   │   ├── tools/*.py
│   │   │   └── prompts/*.md                versioned          [OPUS]
│   │   ├── domain/
│   │   │   ├── calculator.py
│   │   │   └── rules.py                    [OPUS]
│   │   ├── memory/{checkpointer,store}.py
│   │   └── retrieval/{policies,precedents}.py
│   ├── scripts/
│   │   ├── 00_check_atlas.py       connectivity + index-limit probe   ← DAY 1 FIRST
│   │   ├── 01_create_indexes.py
│   │   ├── 02_seed.py              --reembed flag
│   │   └── 03_eval_retrieval.py    recall@3
│   └── tests/
│       ├── test_calculator.py
│       ├── test_rules.py
│       ├── test_policy_consistency.py
│       └── test_graph_smoke.py
├── frontend/                       see [12](12-frontend.md)
└── data/
    ├── policies/*.md               ~30 chunks
    ├── cases/cases.json            ~60 cases
    └── profiles/profiles.json      3–5 customers
```

`.gitignore` has `.temp/` on the first line. That directory must never reach the shared
repository.

The four ADRs exist because "explain each architectural decision in depth" is a scored
criterion, and a written ADR is a better answer than a recollection. Each is short — context,
decision, consequences, alternatives rejected.

---

## 2. Testing strategy

Test where tests pay, given a four-day budget.

| Target | Type | Why |
|---|---|---|
| `domain/calculator.py` | Unit, known-value | Financial arithmetic fails silently and destroys credibility |
| `domain/rules.py` | Unit, boundary values | Every threshold tested at −0.01, exact, +0.01 |
| Policy/code consistency | Unit | Prevents citing a policy the code does not implement ([10 §4](10-domain-credit.md)) |
| Graph end-to-end | Smoke, fake LLM | Wiring, routing, state transitions — not model output |
| Retrieval | `03_eval_retrieval.py` | recall@3 ≥ 0.8 on a golden set ([09](09-retrieval-eval.md)) |

**Deliberately not tested:** LLM node outputs, prompt quality, frontend. These are judged by
rehearsal, not assertions. Writing brittle assertions against model output would consume
Wednesday and protect nothing.

Saying this explicitly — *"here is what I tested and here is what I chose not to test, and
why"* — is a stronger answer than claiming broad coverage.

---

## Acceptance criteria

- [ ] `make setup && make seed && make dev` works from a clean clone with only `.env` filled.
- [ ] `make test` runs green.
- [ ] `make eval` prints the retrieval metrics.
- [ ] `make demo-reset` restores the database to its post-seed state — needed between
      rehearsals and if the live demo needs a restart.
- [ ] `.temp/` is git-ignored and absent from `git ls-files`.
- [ ] README explains reproduction in under ten steps.
- [ ] Four ADRs written.
