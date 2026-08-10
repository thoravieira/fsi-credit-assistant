# SDD 15 — Risks and open items

> Part of the [FSI Credit Assistant SDD](00-overview.md)
> **Review this file every morning.** Risks with a Day 1 deadline are the ones that can
> still be routed around; the same risk discovered Thursday cannot.

---

## 1. Risks

| # | Risk | Impact | Mitigation | Deadline |
|---|---|---|---|---|
| 1 | ~~M0 search index limit~~ | — | **Closed 2026-08-10.** Cluster is a dedicated **M10** (voucher credits), which does not impose the shared-tier index cap. Confirmed by `00_check_atlas.py`: 3 vector search indexes created and reached `queryable` simultaneously | closed |
| 2 | ~~M0 vector search latency~~ | — | **Closed 2026-08-10.** M10 gives dedicated, predictable performance. Measured by `00_check_atlas.py` on Day 1: p50 = 30 ms, p95 = 37 ms (60-doc scratch corpus, well under the 1.5 s budget) | closed |
| 2b | **IP allowlist blocks the venue network on Friday** | Demo dies at the worst possible moment | The allowlist entry added from home/office will not match the venue IP. Add the venue network on arrival, or temporarily allow `0.0.0.0/0` **only** for the presentation and remove it after. Test connectivity from a phone hotspot on Thursday | **Day 4** |
| 3 | Venue network fails | Demo dies | Docker Desktop WSL integration confirmed working 2026-08-10 (`docker run hello-world` pulled and ran successfully). `docker-compose.yml` with the `mongodb/mongodb-atlas-local` offline fallback path itself is not yet written — still needed. **Also record a screen capture of a full successful run on Thursday.** | Day 2 / Day 4 |
| 4 | ~~Docker not currently available in this WSL distro~~ | — | **Closed 2026-08-10.** Docker Desktop WSL integration confirmed: `docker --version` (29.5.3), `docker compose version` (v5.1.4), and a real `docker run hello-world` all succeeded | closed |
| 5 | Executing model writes pre-2026 APIs (`AsyncMongoDBSaver`, `astream_events(version="v2")`, `filter=` instead of `pre_filter=`) | Hours lost debugging | [13](13-verified-api-contract.md) is authoritative and must be cited in every implementation task | Continuous |
| 6 | **Deep Agent latency during live negotiation** | 15 s+ of silence in front of the panel | Deep Agents adds planning plus a round trip per subagent delegation. Stream tokens, render subagent delegation as trace steps, cap iterations, and keep the `AGENT_MODE=deep\|react` fallback flag. **Measure median turn latency Wednesday.** [06 §6](06-negotiation-agent.md) | **Day 3** |
| 7 | Voyage free-tier key not obtained in time | Blocks embeddings | The factory already supports OpenAI at the same 1024 dims; switching is one env var plus `--reembed` ([08 §1](08-retrieval.md)) | Day 1 |
| 8 | Scope overrun on the Next.js frontend | Backend unfinished | Frontend is explicitly cuttable. **The backend must be `curl`-demonstrable by end of Day 2** | Day 2 |

### The ones that actually end the project

With risks 1 and 2 closed by the M10 upgrade, the remaining project-enders are **8** (scope
overrun leaves the backend unfinished) and **2b** (the venue network cannot reach Atlas).

Risk 8 is why the degradation guarantee in [01 §4](01-architecture.md) is a design
constraint rather than a nice idea. Risk 2b is the one most likely to be forgotten, because
it works perfectly every single time you test it at home.

---

## 2. Open items — owned by Thiago, blocking

| Item | Blocks | Resolve by |
|---|---|---|
| Atlas **M10** cluster provisioned, database user scoped to `credit_assistant`, connection string in `.env` | Everything | **Day 1** |
| Voyage AI API key obtained | Seeding, all retrieval | **Day 1** |
| Exact OpenAI chat model id available on the account (goes into `settings.llm_model` and `decisions_log.model`) | All LLM nodes | Day 1 |
| `MongoDBSaver(ttl=...)` behaviour: native TTL index or client-side sweep? | Only the claim made on stage | Day 1 — via `00_check_atlas.py` |
| Docker Desktop WSL integration enabled | The Docker deliverable, risk 3 fallback | Day 2 |
| **Venue IP added to the Atlas allowlist** | The live demo | **Day 4 / on arrival** |
| Confirmed presentation duration | Final demo beat selection | Before Thursday's rehearsal |

Nothing in the build starts before the first two are done.
