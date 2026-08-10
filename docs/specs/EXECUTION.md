# Execution order — one session per row

Ordered by **risk**, not by file number. Start a fresh Claude Code session per row, paste the
prompt, commit at the end, close the session.

## Before session 1 — you, not Claude

- [ ] Atlas M0 cluster created, IP allowlist configured
- [ ] `MONGODB_URI` in hand
- [ ] Voyage AI API key (free tier)
- [ ] Exact OpenAI chat model id available on your account

Nothing below runs without these four.

---

## Day 1 — prove the riskiest assumption

### Session 1 · Scaffold + Atlas probe — **Sonnet**

> Leia `docs/specs/00-overview.md`, `03-atlas-indexes.md` e `14-repo-and-testing.md`.
> Crie o scaffold do backend (uv, pyproject com as versões fixadas em
> `13-verified-api-contract.md` §1, `config.py`, `db.py`, `embeddings.py`, `.env.example`,
> Makefile) e implemente `scripts/00_check_atlas.py` conforme a §3 do SDD 03.
> Não implemente mais nada. Rode o script contra o cluster real e me mostre a saída.

**Gate:** if fewer than 3 vector indexes are allowed, apply the fallback in SDD 03 §3 and
update SDD 15 before continuing.

### Session 2 · Dataset + indexes + retrieval eval — **Sonnet**

> Leia `docs/specs/02-data-model.md`, `03-atlas-indexes.md`, `08-retrieval.md` e
> `09-retrieval-eval.md`.
> Escreva o dataset em `data/` (~30 chunks de política em português, ~60 casos históricos,
> 3 perfis), implemente `01_create_indexes.py`, `02_seed.py` e `03_eval_retrieval.py`.
> Rode os três e me mostre o recall@3.

**Gate — the day's real goal:** `recall@3 ≥ 0.8`. If it fails, fix chunking per SDD 09 §3
before touching the graph. If this does not close Monday night, replan Tuesday morning.

---

## Day 2 — customer flow end to end

### Session 3 · Credit domain — **Sonnet, then Opus for `rules.py`**

> Leia `docs/specs/10-domain-credit.md`. Implemente `domain/calculator.py` e
> `domain/rules.py` com os testes de `tests/`. Zero imports de langchain/langgraph.

### Session 4 · Graph, customer path — **Opus for `builder.py`, Sonnet for the nodes**

> Leia `docs/specs/04-graph-state.md`, `05-graph-nodes-and-routing.md` e `07-memory.md`.
> Implemente o state, o checkpointer, o store, o builder e os nós do caminho da cliente
> (`router` até `customer_response`). Pare antes do caminho do analista.

### Session 5 · FastAPI + SSE — **Sonnet**

> Leia `docs/specs/11-api-sse.md`. Implemente `main.py` com os endpoints e o contrato SSE.

**Gate:** `curl -N -X POST localhost:8000/api/chat` streams real trace events.

---

## Day 3 — analyst flow and UI

### Session 6 · Negotiation agent — **Opus**

> Leia `docs/specs/06-negotiation-agent.md`, `04-graph-state.md` e `10-domain-credit.md`.
> Implemente `precedent_search`, `analyst_brief`, o nó `negotiation` com as 4 tools,
> `await_approval` com `interrupt()` e `persist_decision`.

### Session 7 · Frontend — **Sonnet**

> Leia `docs/specs/12-frontend.md` e `11-api-sse.md`. Implemente o app Next.js.
> Atenção: SSE via `fetch` + `ReadableStream`, nunca `EventSource`.

---

## Day 4 — docs and rehearsal

### Session 8 · Documentation — **Sonnet**

> Leia `docs/specs/14-repo-and-testing.md`, `16-demo-plan.md` e `17-objection-bank.md`.
> Escreva README, os 4 ADRs, `docs/architecture.md`, `docs/demo-script.md`,
> `docs/objection-bank.md` e `docs/slides-outline.md`.

### Then, you alone

- [ ] Two full timed rehearsals
- [ ] Beat 7 (kill and resume) rehearsed twice
- [ ] Screen recording of a complete successful run

---

## Rules for every session

1. **Name the spec files in the prompt.** Do not let Claude read all 18.
2. **Commit at the end of each session**, then close it. Fresh context per session is
   cheaper and produces better code than one long session.
3. **When the acceptance criteria in the spec pass, stop.** Do not accept scope expansion.
4. If a spec turns out to be wrong, **fix the spec first**, then the code. The spec is the
   source of truth for the sessions that come after.
