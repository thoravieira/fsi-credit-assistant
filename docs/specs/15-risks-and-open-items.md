# SDD 15 — Risks and open items

> Part of the [FSI Credit Assistant SDD](00-overview.md)
> **Review this file every morning.** Risks with a Day 1 deadline are the ones that can
> still be routed around; the same risk discovered Thursday cannot.

---

## 1. Risks

| # | Risk | Impact | Mitigation | Deadline |
|---|---|---|---|---|
| 1 | M0 allows fewer search indexes than needed (limit unconfirmed, possibly 3) | Blocks the whole retrieval design | `00_check_atlas.py` probes it first. Two fallbacks already designed in [03 §3](03-atlas-indexes.md) | **Day 1, hour 1** |
| 2 | M0 vector search latency makes the live demo drag | Demo feels slow in front of the panel | Measure on Day 1. If p95 > 1.5 s: reduce `k`, reduce corpus, or upgrade tier | Day 1 |
| 3 | Venue network fails | Demo dies | Enable Docker Desktop WSL integration and validate the `mongodb/mongodb-atlas-local` compose path as an offline fallback. **Also record a screen capture of a full successful run on Thursday.** | Day 2 / Day 4 |
| 4 | Docker not currently available in this WSL distro | The "reproduce locally" deliverable ships untested | Enable integration Day 1–2. If not enabled by Wednesday, mark the compose file explicitly as untested in the README rather than implying it works | Day 2 |
| 5 | Executing model writes pre-2026 APIs (`AsyncMongoDBSaver`, `astream_events(version="v2")`, `filter=` instead of `pre_filter=`) | Hours lost debugging | [13](13-verified-api-contract.md) is authoritative and must be cited in every implementation task | Continuous |
| 6 | LLM latency during live negotiation | Awkward silences on stage | Cap `max_tokens`, stream tokens (already in the SSE contract), pre-warm the connection at app start | Day 3 |
| 7 | Voyage free-tier key not obtained in time | Blocks embeddings | The factory already supports OpenAI at the same 1024 dims; switching is one env var plus `--reembed` ([08 §1](08-retrieval.md)) | Day 1 |
| 8 | Scope overrun on the Next.js frontend | Backend unfinished | Frontend is explicitly cuttable. **The backend must be `curl`-demonstrable by end of Day 2** | Day 2 |

### The two that actually end the project

Risks 1 and 8. Everything else degrades the demo; these two prevent it.

Risk 1 is why `00_check_atlas.py` is the first thing built. Risk 8 is why the degradation
guarantee in [01 §4](01-architecture.md) is a design constraint rather than a nice idea.

---

## 2. Open items — owned by Thiago, blocking

| Item | Blocks | Resolve by |
|---|---|---|
| Atlas M0 cluster provisioned, IP allowlist configured, connection string in `.env` | Everything | **Day 1** |
| Voyage AI API key obtained | Seeding, all retrieval | **Day 1** |
| Exact OpenAI chat model id available on the account (goes into `settings.llm_model` and `decisions_log.model`) | All LLM nodes | Day 1 |
| M0 search index limit confirmed empirically | [03](03-atlas-indexes.md) | Day 1 — via `00_check_atlas.py` |
| `MongoDBSaver(ttl=...)` behaviour: native TTL index or client-side sweep? | Only the claim made on stage | Day 1 — via `00_check_atlas.py` |
| Docker Desktop WSL integration enabled | The Docker deliverable, risk 3 fallback | Day 2 |
| Confirmed presentation duration | Final demo beat selection | Before Thursday's rehearsal |

Nothing in the build starts before the first two are done.
