# SDD 00 — Overview and Index

| | |
|---|---|
| **Status** | Approved (design), pending implementation plan |
| **Author** | Thiago da Hora |
| **Date** | 2026-08-10 |
| **Demo date** | 2026-08-14 (Friday), 45–60 min + Q&A |
| **Purpose** | Technical demo for a MongoDB Solutions Architect interview |

---

## How to use this specification

This is a **spec set**, not a single document. Each file below is a self-contained unit of
work: it states what it depends on, what it produces, and how to know it is done. Load only
the files a task needs.

Three rules that apply to every file:

1. **[13 — Verified API Contract](13-verified-api-contract.md) overrides memory.** Every
   signature there was obtained by introspecting the installed package on 2026-08-10.
   Published documentation is stale in at least three places. If code you are about to
   write disagrees with file 13, file 13 is right.
2. **Tasks marked [OPUS]** need a high-reasoning model. Everything else targets Sonnet.
3. **Acceptance criteria are binding.** A file is not implemented until its criteria pass.

---

## Index

### Foundations

| # | File | Contents | Model |
|---|---|---|---|
| 01 | [Architecture](01-architecture.md) | System diagram, the central thesis, component responsibilities, degradation guarantee | — |
| 02 | [Data model](02-data-model.md) | The 8 collections and their document schemas | Sonnet |
| 03 | [Atlas indexes](03-atlas-indexes.md) | Standard + vector indexes, the M0 index-limit probe, fallback plan | Sonnet |

### The agent

| # | File | Contents | Model |
|---|---|---|---|
| 04 | [Graph state](04-graph-state.md) | `AgentState`, the one-thread-two-personas design, stage transitions, compilation | Sonnet |
| 05 | [Graph nodes and routing](05-graph-nodes-and-routing.md) | All nodes except negotiation; edges and routing functions | Sonnet |
| 06 | [Negotiation agent](06-negotiation-agent.md) | ReAct node, 4 tools, prompt contract | **[OPUS]** |
| 07 | [Memory](07-memory.md) | Short-term checkpointer, long-term store, namespaces, the durability beat | Sonnet |

### Knowledge and domain

| # | File | Contents | Model |
|---|---|---|---|
| 08 | [Retrieval](08-retrieval.md) | Embeddings, what gets embedded and why, query construction, the precedent loop | Sonnet |
| 09 | [Retrieval evaluation](09-retrieval-eval.md) | Golden set, recall@3, healthy threshold | Sonnet |
| 10 | [Credit domain](10-domain-credit.md) | PMT/CET/LTV/DTI, the decision matrix, policy–code consistency invariant | **[OPUS]** for `rules.py` |

### Delivery surface

| # | File | Contents | Model |
|---|---|---|---|
| 11 | [API and SSE](11-api-sse.md) | Endpoints, SSE event contract, how events are produced | Sonnet |
| 12 | [Frontend](12-frontend.md) | Next.js routes, components, the `EventSource` trap | Sonnet |

### Build discipline

| # | File | Contents | Model |
|---|---|---|---|
| 13 | [Verified API contract](13-verified-api-contract.md) | Literal signatures, pinned versions. **Authoritative.** | — |
| 14 | [Repo layout and testing](14-repo-and-testing.md) | Directory structure, what gets tested and what does not | Sonnet |
| 15 | [Risks and open items](15-risks-and-open-items.md) | 8 risks with deadlines, 6 open items owned by Thiago | — |

### Presentation

| # | File | Contents | Model |
|---|---|---|---|
| 16 | [Demo plan](16-demo-plan.md) | Build schedule, 11 demo beats, what is cuttable | — |
| 17 | [Objection bank](17-objection-bank.md) | 9 likely objections, each anchored to something actually built | — |

---

## Reading paths

**Implementing a backend task:** 00 → 13 → the specific file → 02/03 if it touches data.

**Implementing the frontend:** 00 → 11 → 12.

**Preparing to present:** 00 → 01 → 16 → 17.

**Reviewing the whole design:** 01 → 04 → 07 → 08 → 10, in that order. Those five carry the
argument; the rest is execution detail.

---

## 1. Context and goals

We are building a credit-origination copilot for a fictional retail bank, covering
Brazilian personal credit (mortgage, auto). The demo must prove, live, that MongoDB Atlas
can serve as the **single data plane for an agentic system**: operational data, agent
short-term state, agent long-term memory, and vector search — one cluster, one driver.

### Mandatory requirements (from the interview brief)

| # | Requirement | Satisfied in |
|---|---|---|
| R1 | LangGraph orchestrates the agent flow | [04](04-graph-state.md), [05](05-graph-nodes-and-routing.md) |
| R2 | Short-term memory in MongoDB Atlas | [07 §1](07-memory.md) — `MongoDBSaver` |
| R3 | Long-term memory in MongoDB Atlas | [07 §2](07-memory.md) — `MongoDBStore` (`BaseStore`) |
| R4 | LLM with real reasoning and actions | [06](06-negotiation-agent.md) — ReAct negotiation node |
| R5 | Atlas Vector Search: ingest, index, real semantic query in-graph | [03](03-atlas-indexes.md), [08](08-retrieval.md) |
| R6 | Architecture diagram (graph nodes, memory R/W, vector search) | [01](01-architecture.md) |

### Evaluation criteria (what the panel scores)

Business value · discovery · audience engagement · communication clarity · handling live
objections. The panel role-plays the customer/analyst.

This means [16 — Demo plan](16-demo-plan.md) and [17 — Objection bank](17-objection-bank.md)
are **first-class deliverables, not afterthoughts**. Budget real time for them on Thursday.

### Success criteria

1. Demo runs live without failing.
2. Every architectural decision can be defended in depth.
3. Business objections have prepared, architecture-anchored answers.
4. Git repo is shareable: code, Docker, seed scripts, diagrams, prompts, reproduction steps.

---

## 2. Non-goals

Explicitly out of scope. Stating these prevents scope creep and gives crisp answers when
the panel asks "why didn't you…?"

- **Real credit bureau / real customer data.** All data is synthetic. LGPD-safe by
  construction.
- **Authentication, multi-tenancy, RBAC.** Persona switching is a UI toggle. Called out
  explicitly in the objection bank as a known production gap.
- **Model fine-tuning.** The system learns via the precedent loop
  ([08 §4](08-retrieval.md)), not weights.
- **Full amortisation schedule UI.** The calculator returns a 3-row preview only.
- **Horizontal scale testing.** Scale is discussed architecturally, not benchmarked.
- **Sharding, Atlas Search node separation, replica-set tuning.** Discussed in the
  objection bank; not implemented on M0.

---

## The three-layer stack

Tools are chosen per problem type, not by applying the newest one everywhere. Detail in
[06 §1](06-negotiation-agent.md).

| Layer | Technology | Where |
|---|---|---|
| Conversation | **LangChain** | `intake`, `customer_response`, `analyst_brief` |
| Workflow | **LangGraph** | `router` → `decision`, `persist_decision`, `await_approval` |
| Reasoning | **Deep Agents** | `negotiation` only |

The `router` is **deterministic Python**, not an LLM. An LLM at the entry point of every
request adds latency and a failure mode to the one component that must never be
unpredictable. LangChain is the LLM *interaction* layer, not the dispatch layer.

---

## Conventions

- **Repository language is English** (code, comments, docs, ADRs, diagrams).
- **Demo-facing content is Portuguese** (UI copy, policy corpus, agent responses, seeded
  case narratives). The Brazilian credit domain — CET, Tabela Price, comprometimento de
  renda, SFH — is a strength in front of this panel, not an accident.
- Prompts live in `backend/app/graph/prompts/*.md`, versioned, and the version string is
  written into every `decisions_log` entry.
