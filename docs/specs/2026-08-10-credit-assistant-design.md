# SDD — FSI Credit Assistant (MongoDB Technical Demo)

| | |
|---|---|
| **Status** | Approved (design), pending implementation plan |
| **Author** | Thiago Vieira |
| **Date** | 2026-08-10 |
| **Demo date** | 2026-08-14 (Friday), 45–60 min + Q&A |
| **Purpose** | Technical demo for a MongoDB Solutions Architect interview |

> **How to use this document.** This is the single source of truth for the build. Every
> API signature in [§11](#11-verified-api-contract) was verified by introspecting the
> actually-installed package — not from documentation, which is stale in several places.
> When implementing, prefer the literal signatures in §11 over anything remembered from
> training data.
>
> Tasks marked **[OPUS]** should be implemented with a high-reasoning model. Everything
> else is intended for Sonnet.

---

## 1. Context and goals

We are building a credit-origination copilot for a fictional retail bank, covering
Brazilian personal credit (mortgage, auto). The demo must prove, live, that MongoDB Atlas
can serve as the **single data plane for an agentic system**: operational data, agent
short-term state, agent long-term memory, and vector search — one cluster, one driver.

### Mandatory requirements (from the interview brief)

| # | Requirement | Where it is satisfied |
|---|---|---|
| R1 | LangGraph orchestrates the agent flow | [§5](#5-langgraph-design) |
| R2 | Short-term memory in MongoDB Atlas | `MongoDBSaver` checkpointer, [§6.1](#61-short-term-memory) |
| R3 | Long-term memory in MongoDB Atlas | `MongoDBStore` (`BaseStore`), [§6.2](#62-long-term-memory) |
| R4 | LLM with real reasoning and actions | Negotiation ReAct node, [§5.4](#54-the-negotiation-node-opus) |
| R5 | Atlas Vector Search: ingest, index, real semantic query in-graph | [§7](#7-retrieval-design) |
| R6 | Architecture diagram (graph nodes, memory R/W, vector search) | [§3](#3-architecture-overview) + `docs/diagrams/` |

### Evaluation criteria (what the panel scores)

Business value · discovery · audience engagement · communication clarity · handling live
objections. The panel role-plays the customer/analyst. This means **the objection bank
(§16) and the demo script (§15) are first-class deliverables, not afterthoughts.**

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
  explicitly in the objection bank as "known production gap".
- **Model fine-tuning.** The system learns via the precedent loop (§7.4), not weights.
- **Full amortisation schedule UI.** Calculator returns a 3-row preview only.
- **Horizontal scale testing.** Scale is discussed architecturally, not benchmarked.
- **Sharding, Atlas Search node separation, replica-set tuning.** Discussed in the
  objection bank; not implemented on M0.

---

## 3. Architecture overview

```mermaid
flowchart TB
    subgraph client["Next.js (single app, two routes)"]
        MARIANA["/ · Mariana (customer)"]
        CARLOS["/console · Carlos (analyst)"]
        TRACE["TracePanel (shared component)"]
    end

    subgraph api["FastAPI"]
        CHAT["POST /api/chat · SSE"]
        APPS["/api/applications"]
        APPROVE["POST /api/approve"]
    end

    subgraph graph["LangGraph · one thread per application"]
        ROUTER[router]
        INTAKE[intake]
        CTX[load_context]
        POL[policy_retrieval]
        CALC[credit_calculator]
        DEC[decision]
        CRESP[customer_response]
        PREC[precedent_search]
        BRIEF[analyst_brief]
        NEG["negotiation · ReAct + 4 tools"]
        WAIT["await_approval · interrupt()"]
        PERSIST[persist_decision]
    end

    subgraph atlas["MongoDB Atlas M0 · database: credit_assistant"]
        CKPT[("checkpoints<br/>checkpoint_writes<br/><i>short-term · TTL</i>")]
        MEM[("agent_memories<br/><i>long-term · BaseStore</i>")]
        PROF[("customer_profiles")]
        POLC[("credit_policies<br/><i>vector index</i>")]
        CASES[("historical_cases<br/><i>vector index</i>")]
        APPSC[("applications")]
        LOG[("decisions_log<br/><i>append-only</i>")]
    end

    MARIANA --> CHAT
    CARLOS --> CHAT
    CARLOS --> APPROVE
    CHAT -->|SSE trace events| TRACE
    CHAT --> ROUTER

    ROUTER --> INTAKE --> CTX --> POL --> CALC --> DEC
    DEC --> CRESP
    ROUTER --> PREC --> BRIEF
    ROUTER --> NEG --> WAIT --> PERSIST

    graph -.->|read+write every superstep| CKPT
    CTX -.->|read| MEM
    CTX -.->|read| PROF
    POL -.->|$vectorSearch| POLC
    PREC -.->|$vectorSearch| CASES
    PERSIST -.->|write| LOG
    PERSIST -.->|write new precedent| CASES
    PERSIST -.->|write| MEM
    DEC -.->|update status| APPSC
```

### The central thesis

One database serves four workloads that a conventional stack splits across four systems:

| Workload | Conventional stack | Here |
|---|---|---|
| Operational records | PostgreSQL | `applications`, `customer_profiles` |
| Agent state / checkpoints | Redis | `checkpoints` (+ TTL index) |
| Long-term agent memory | PostgreSQL + pgvector | `agent_memories` |
| Vector search | Pinecone / Weaviate | `credit_policies`, `historical_cases` |

Fewer moving parts, one consistency model, one driver, one connection pool, one backup
policy, one access-control surface. This is the argument the demo makes.

---

## 4. Data model

Database: `credit_assistant`.

### 4.1 Collections

| Collection | Owner | Notes |
|---|---|---|
| `checkpoints` | `MongoDBSaver` | Created and managed by the library. Do not hand-write. |
| `checkpoint_writes` | `MongoDBSaver` | Idem. |
| `agent_memories` | `MongoDBStore` | Created and managed by the library. |
| `customer_profiles` | seed script | Read-only at runtime. |
| `credit_policies` | seed script | Vector index. Read-only at runtime. |
| `historical_cases` | seed + agent | Vector index. **Written by `persist_decision`.** |
| `applications` | API + graph | Mutable state of each credit request. |
| `decisions_log` | graph | Append-only audit trail. Never updated, never deleted. |

### 4.2 `customer_profiles`

```json
{
  "_id": "CUST-0001",
  "name": "Mariana Duarte",
  "cpf_masked": "***.456.789-**",
  "birth_date": "1990-04-17",
  "employment": {
    "type": "clt",
    "employer": "Rede Aurora Varejo",
    "tenure_months": 74,
    "occupation": "Gerente de operações"
  },
  "income": { "gross_monthly": 14500.0, "net_monthly": 11200.0, "verified": true,
              "verification_method": "holerite" },
  "credit": { "internal_score": 782, "bureau_score": 741,
              "existing_monthly_debt": 1350.0, "delinquency_last_24m": false },
  "relationship": { "customer_since": "2016-03-01", "tenure_months": 125,
                    "products": ["conta_corrente", "cartao_credito", "seguro_auto"],
                    "avg_balance_12m": 18400.0, "salary_portability": true },
  "open_finance": {
    "consent_granted": false,
    "shareable_assets": [
      { "institution": "Corretora Meridiano", "type": "cdb", "balance": 96000.0,
        "liquidity": "d_plus_1" },
      { "institution": "Corretora Meridiano", "type": "fundo_multimercado",
        "balance": 42000.0, "liquidity": "d_plus_30" }
    ]
  }
}
```

`open_finance.consent_granted` starting at `false` is deliberate: it is the lever Carlos
pulls during negotiation, and the moment where a *business* concept (Open Finance consent)
becomes an *agent action* on screen.

### 4.3 `credit_policies`

One document per policy chunk. ~30 documents.

```json
{
  "_id": "POL-014",
  "policy_type": "ltv_limit",
  "product": "mortgage",
  "title": "Limite de LTV para financiamento imobiliário residencial",
  "text": "O valor financiado não poderá exceder 80% do valor de avaliação do imóvel ...",
  "effective_from": "2026-01-01",
  "version": "2026.1",
  "authority_level": "comite_credito",
  "embedding": [/* 1024 floats */]
}
```

`text` is the embedded field. Full prose, self-contained, 80–200 words — a chunk must be
readable on its own when shown in the trace panel, because it *will* be shown on screen.

**Policy families to author (~30 chunks):** LTV limits by product · maximum DTI
(comprometimento de renda) · age + term ≤ 80 years rule · minimum score bands · FGTS
usage · income verification for self-employed (DECORE) · alternative collateral · Open
Finance asset sharing as a risk mitigant · rate spread table by LTV × score · approval
authority levels (alçadas) · restrictions on properties in probate/inventory.

### 4.4 `historical_cases`

~60 seeded + grown live by the agent.

```json
{
  "_id": "CASE-2025-0417",
  "product": "mortgage",
  "summary": "Cliente CLT com 6 anos de casa solicitou financiamento de R$ 380 mil ...",
  "structured": {
    "requested_amount": 380000, "asset_value": 475000, "term_months": 360,
    "ltv": 0.80, "dti": 0.34, "internal_score": 715, "employment_type": "clt"
  },
  "decision": "approved_with_conditions",
  "final_rate_annual": 0.1145,
  "conditions": ["aumento de entrada para 25%", "seguro MIP obrigatório"],
  "rationale": "DTI acima do limite automático de 30%, compensado por relacionamento ...",
  "decided_by": "ANALYST-CARLOS",
  "decided_at": "2025-11-08T14:22:00Z",
  "ltv_band": "high",
  "embedding": [/* 1024 floats */]
}
```

**`summary` is the embedded field, and it is prose — never a JSON dump.** See §7.2 for why.

### 4.5 `applications`

```json
{
  "_id": "APP-20260814-0001",
  "thread_id": "APP-20260814-0001",
  "customer_id": "CUST-0001",
  "product": "mortgage",
  "asset_value": 560000.0,
  "down_payment": 112000.0,
  "requested_amount": 448000.0,
  "term_months": 360,
  "purpose": "Aquisição de imóvel residencial próprio",
  "status": "manual_review",
  "created_at": "2026-08-14T13:02:11Z",
  "updated_at": "2026-08-14T13:02:19Z",
  "latest_assessment": { /* CalcResult + decision, denormalised for the queue UI */ }
}
```

`status` ∈ `draft` | `auto_approved` | `manual_review` | `approved` | `approved_with_conditions` | `denied`.

**`thread_id` equals `_id`.** This is the mechanism by which Mariana and Carlos share one
LangGraph thread (§5.1).

### 4.6 `decisions_log`

Append-only. Every assessment *and* every discarded negotiation scenario is written here.

```json
{
  "_id": { "$oid": "..." },
  "application_id": "APP-20260814-0001",
  "thread_id": "APP-20260814-0001",
  "seq": 3,
  "event_type": "scenario_simulated",
  "actor": { "type": "analyst", "id": "ANALYST-CARLOS" },
  "inputs": { "down_payment": 168000.0, "term_months": 360 },
  "calc": { "monthly_payment": 4218.44, "ltv": 0.70, "dti": 0.302, "cet_annual": 0.1291 },
  "outcome": "eligible_auto",
  "policy_refs": ["POL-014", "POL-021"],
  "precedent_refs": ["CASE-2025-0417"],
  "rationale": "Com entrada de 30% o LTV cai para 70% ...",
  "model": "<settings.llm_model>", "prompt_version": "v1",
  "created_at": "2026-08-14T13:05:44Z"
}
```

`event_type` ∈ `assessment` | `scenario_simulated` | `recommendation` | `human_approval` | `final_decision`.

Recording *discarded* scenarios is the point. A regulator does not want the final answer;
they want the path. This single design choice answers "how do you guarantee
explainability?" with a query instead of a claim.

**Every path writes here — including automatic approvals.** The `decision` node writes an
`assessment` event directly, before the customer ever sees an answer. An audit trail that
only covers the cases a human touched is not an audit trail.

### 4.7 Indexes

**Standard indexes**

```
applications:   { status: 1, created_at: -1 }
decisions_log:  { application_id: 1, seq: 1 }
customer_profiles: _id is the customer id (no extra index)
```

**Vector search indexes** — 1024 dimensions, `cosine`, created by `scripts/01_create_indexes.py`.

| Collection | Index name | Path | Filter fields |
|---|---|---|---|
| `credit_policies` | `vector_index` | `embedding` | `product`, `policy_type` |
| `historical_cases` | `vector_index` | `embedding` | `product`, `decision`, `ltv_band` |
| `agent_memories` | `vector_index` | `embedding` | (managed by `MongoDBStore`) |

> ⚠️ **Day-1 blocker check.** The number of Atlas Search indexes allowed on an M0 free
> cluster could not be confirmed from primary MongoDB documentation; third-party sources
> suggest a limit of 3. `scripts/00_check_atlas.py` must verify this before anything else
> is built. **Fallback if the limit bites:** instantiate `MongoDBStore` *without*
> `index_config`, making long-term memory pure key-value (semantic search over memories is
> not required by any demo beat). That reduces the requirement to 2 vector indexes.

---

## 5. LangGraph design

### 5.1 One thread, two personas

`thread_id == application_id`. Mariana's simulation creates the thread. When the decision
is `MANUAL_REVIEW`, the application lands in Carlos's queue carrying that same
`thread_id`. Carlos resumes the *same* thread.

Consequence: the full context of Mariana's conversation is available to Carlos's agent
without any explicit handoff payload, because it lives in `checkpoints` on Atlas rather
than in a process's memory. This is a demo beat, not an implementation detail.

### 5.2 State schema

`backend/app/graph/state.py`:

```python
from typing import Annotated, Literal, TypedDict
import operator
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class CreditApplication(TypedDict):
    application_id: str
    customer_id: str
    product: Literal["mortgage", "auto"]
    asset_value: float
    down_payment: float
    requested_amount: float
    term_months: int
    purpose: str


class CalcResult(TypedDict):
    monthly_payment: float
    total_interest: float
    annual_rate: float
    cet_annual: float
    ltv: float
    dti: float
    schedule_preview: list[dict]


class Decision(TypedDict):
    outcome: Literal["auto_approved", "manual_review", "denied"]
    reasons: list[str]
    policy_refs: list[str]
    breached_rules: list[str]


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    persona: Literal["customer", "analyst"]
    stage: Literal["intake", "assessment", "review", "negotiation", "closed"]
    application: CreditApplication | None
    profile: dict | None
    memories: list[dict]
    policies: list[dict]
    precedents: list[dict]
    calc: CalcResult | None
    decision: Decision | None
    scenarios: Annotated[list[dict], operator.add]
    pending_approval: dict | None
```

Note `scenarios` uses `operator.add` so every negotiation scenario accumulates rather than
overwrites — the scenario history is itself demo material ("look, we tried five
structures in ninety seconds").

### 5.3 Nodes

| Node | Type | Responsibility |
|---|---|---|
| `router` | deterministic | Dispatch on `persona` + `stage`. Pure function, no I/O. |
| `intake` | LLM (structured output) | Extract/normalise loan parameters from free text into `CreditApplication`. If required fields are missing, set `application=None` and route back to ask. |
| `load_context` | deterministic | Read `customer_profiles` + `MongoDBStore` memories into state. |
| `policy_retrieval` | vector search | `$vectorSearch` on `credit_policies`, `pre_filter` by product. k=4. |
| `credit_calculator` | **pure Python** | PMT, CET, LTV, DTI. No LLM. See §8. |
| `decision` | deterministic rules | Apply `domain/rules.py` → `auto_approved` / `manual_review` / `denied`. Writes an `assessment` event to `decisions_log` and updates `applications.status` + `latest_assessment`. |
| `customer_response` | LLM | Write Mariana's answer in plain Portuguese, grounded in `policies` + `calc`. |
| `precedent_search` | vector search | `$vectorSearch` on `historical_cases`, `pre_filter` by product. k=3. |
| `analyst_brief` | LLM | Produce the case dossier: recommendation + explainability + precedent citations. |
| `negotiation` | **ReAct agent** | Handle Carlos's "what if" turns. 4 tools. **[OPUS]** |
| `await_approval` | `interrupt()` | Pause and persist before any write to `decisions_log`. |
| `persist_decision` | deterministic | Write log entry, new precedent (with embedding), memory updates. |

### 5.4 The negotiation node [OPUS]

The only genuinely agentic component. `create_react_agent` with four tools:

```python
recalculate_scenario(amount: float, term_months: int,
                     down_payment: float, annual_rate: float | None) -> CalcResult
search_policy(query: str, product: str) -> list[PolicyChunk]
search_precedents(query: str, product: str, decision: str | None) -> list[Case]
check_open_finance_assets(customer_id: str) -> OpenFinanceAssets
```

`recalculate_scenario` delegates to `domain/calculator.py` — the LLM never computes a
number. This separation is the answer to "how do you stop it hallucinating financials?":
**the model chooses the scenario, arithmetic is deterministic code.**

The node's system prompt must:
1. State the analyst's role and that recommendations require human approval.
2. Require citing policy IDs for any eligibility claim.
3. Forbid asserting any figure not returned by `recalculate_scenario`.
4. Instruct that when Carlos signals a final decision ("aprovar", "negar", "aprovar com
   condições"), it sets `pending_approval` rather than concluding on its own.

All prompts live in `backend/app/graph/prompts/` as versioned `.md` files, and the version
string is written into `decisions_log.prompt_version`. Prompt provenance is part of the
audit trail — another free objection answer.

### 5.5 Edges

```python
builder.add_edge(START, "router")
builder.add_conditional_edges("router", route, {
    "intake": "intake",
    "precedent_search": "precedent_search",
    "negotiation": "negotiation",
})

# customer path
builder.add_conditional_edges("intake", has_complete_application, {
    "complete": "load_context",
    "incomplete": "customer_response",      # ask for the missing fields
})
builder.add_edge("load_context", "policy_retrieval")
builder.add_edge("policy_retrieval", "credit_calculator")
builder.add_edge("credit_calculator", "decision")
builder.add_edge("decision", "customer_response")
builder.add_edge("customer_response", END)

# analyst path
builder.add_edge("precedent_search", "analyst_brief")
builder.add_edge("analyst_brief", END)

builder.add_conditional_edges("negotiation", needs_approval, {
    "await_approval": "await_approval",
    "end": END,
})
builder.add_edge("await_approval", "persist_decision")
builder.add_edge("persist_decision", END)
```

Routing function:

```python
def route(state: AgentState) -> str:
    if state["persona"] == "analyst":
        return "precedent_search" if state["stage"] == "review" else "negotiation"
    return "intake"


def has_complete_application(state: AgentState) -> str:
    app = state.get("application")
    required = ("product", "asset_value", "down_payment", "term_months")
    return "complete" if app and all(app.get(f) is not None for f in required) else "incomplete"


def needs_approval(state: AgentState) -> str:
    return "await_approval" if state.get("pending_approval") else "end"
```

**Stage transitions** (exhaustive — every node that mutates `stage` is listed):

| Node | Sets `stage` to | When |
|---|---|---|
| `intake` | `assessment` | application is complete |
| `intake` | `intake` (unchanged) | fields missing |
| `decision` | `review` | outcome is `manual_review` |
| `decision` | `closed` | outcome is `auto_approved` or `denied` |
| `analyst_brief` | `negotiation` | always |
| `persist_decision` | `closed` | always |

Note that `route()` sends a customer turn to `intake` regardless of stage. This is
intentional: a re-simulation ("e se eu desse mais entrada?") is just a new intake against
the same thread, and `intake` sees the prior application in state, so it patches rather
than re-asks.

### 5.6 Compilation

```python
graph = builder.compile(checkpointer=checkpointer, store=store)
```

Both are `compile()` parameters — verified signature in §11.

---

## 6. Memory design

The demo must show that short-term and long-term memory are *different mechanisms*, not
the same store with different TTLs.

| | Short-term | Long-term |
|---|---|---|
| What | Serialised graph state per superstep | Structured knowledge about people |
| Shape | Opaque blob, library-managed | Queryable documents, app-defined |
| Lifetime | TTL 24h | Permanent |
| Mechanism | `MongoDBSaver` (checkpointer) | `MongoDBStore` (`BaseStore`) |
| Purpose | Resume, replay, time-travel, durability | Personalisation, calibration, eligibility facts |

### 6.1 Short-term memory

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

> **Do not import `AsyncMongoDBSaver`.** It does not exist in
> `langgraph-checkpoint-mongodb` 0.4.0 — `langgraph.checkpoint.mongodb.aio` raises
> `ModuleNotFoundError`. `MongoDBSaver` already implements the async protocol methods
> (`aget_tuple`, `alist`, `aput`, `aput_writes`) and works with `graph.ainvoke()` /
> `graph.astream()`. This is verified by introspection; the readthedocs page describing
> `AsyncMongoDBSaver` is stale.

The `ttl` parameter's behaviour (native TTL index vs. client-side sweep) is **unverified**.
`scripts/00_check_atlas.py` should print `db.checkpoints.index_information()` so we know
which it is before claiming anything about it on stage.

### 6.2 Long-term memory

Three namespaces, matching the three memory types chosen for the demo:

| Namespace | Contents | Written by |
|---|---|---|
| `("customer", customer_id, "preferences")` | "Prioritises lower instalment over shorter term"; "reluctant to use FGTS" | `persist_decision`, and an extraction step in `customer_response` |
| `("customer", customer_id, "facts")` | "Self-employed, income via DECORE"; "property in probate — legal block" | `intake` / `negotiation` when a hard fact surfaces |
| `("analyst", analyst_id, "decision_patterns")` | "Carlos accepts DTI up to 33% when Open Finance assets are shared" | `persist_decision`, derived from approved scenarios |

```python
from langgraph.store.mongodb import MongoDBStore, create_vector_index_config

index_config = create_vector_index_config(
    dims=1024,
    embed=get_embeddings(),          # factory, §7.1
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

Value shape written by the app:

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

`content` is the field named in `fields=[...]`, so it is the embedded one.

> **Note:** `MongoDBStore` 0.3.0 has **no** `rerank_config` parameter, contrary to some
> documentation. Constructor params are `(collection, ttl_config, index_config,
> auto_index_timeout, query_model, **kwargs)`. Verified by introspection.

### 6.3 The durability demo beat

Mid-negotiation, kill the backend process (`Ctrl+C`), restart it, send the next message.
The conversation continues with full context because state lives in `checkpoints` on
Atlas. Twenty seconds; proves the architecture better than any slide.

**Precondition:** the FastAPI process must hold no conversational state in memory. Every
request reconstructs from the checkpointer. Enforced by design — the graph is rebuilt per
process, never per session.

---

## 7. Retrieval design

### 7.1 Embeddings

`voyage-4-lite`, 1024 dimensions, via `langchain-voyageai`. Voyage AI is a MongoDB company
and the officially recommended embedding provider for Atlas Vector Search — a deliberate,
defensible choice for this audience. Free tier is 200M tokens; the entire dataset costs
roughly 50k tokens.

`backend/app/embeddings.py` is a factory keyed on `EMBEDDING_PROVIDER`:

```python
def get_embeddings() -> Embeddings:
    if settings.embedding_provider == "voyage":
        from langchain_voyageai import VoyageAIEmbeddings
        return VoyageAIEmbeddings(model="voyage-4-lite", output_dimension=1024)
    from langchain_openai import OpenAIEmbeddings
    return OpenAIEmbeddings(model="text-embedding-3-small", dimensions=1024)
```

Both are pinned to **1024 dimensions** so the vector index definition is provider-agnostic
and switching providers never requires reindexing dimension changes. `text-embedding-3-small`
supports Matryoshka truncation via `dimensions`; `voyage-4-lite` via `output_dimension`.
Both verified present in the installed packages.

> Switching providers still requires **re-embedding** the corpus (`scripts/02_seed.py --reembed`),
> because the vectors themselves are not interchangeable. Only the index schema is stable.

### 7.2 What gets embedded, and why it matters

**Policies:** the `text` field — full prose policy language.

**Cases:** the `summary` field — a narrative paragraph, never a serialisation of the
structured fields.

This is a deliberate technical position worth articulating on stage. Cosine similarity
between `{"ltv": 0.80}` and `{"ltv": 0.75}` is noise; numeric fields carry no semantic
signal in embedding space. What carries signal is *"autônomo com LTV alto, compensado por
relacionamento longo e ativos compartilhados via Open Finance"*. Therefore:

- **Prose → the vector index.** Semantics, similarity, "cases like this one".
- **Numbers → `filter` fields on the index.** Exact constraints, pre-filtered at query time.

Atlas pre-filtering (as opposed to post-filtering) is what makes this split work without
destroying recall: the filter is applied during the ANN traversal, so `k=3` returns three
*eligible* results rather than three results that might all be filtered away afterwards.

### 7.3 Query construction

`policy_retrieval` builds its query from the application, not from raw user text:

```python
query = (f"{product} com LTV de {ltv:.0%}, prazo de {term_months} meses, "
         f"comprometimento de renda de {dti:.0%}, cliente {employment_type}")
docs = vector_store.similarity_search(query, k=4, pre_filter={"product": product})
```

Note the parameter is **`pre_filter`**, not `filter` — verified signature, §11.

`precedent_search` builds a natural-language case description and filters by `product`,
optionally by `ltv_band`.

### 7.4 The precedent loop

`persist_decision` writes the just-decided case into `historical_cases` **with a freshly
generated embedding**, making it immediately retrievable. The system improves without
retraining anything.

This is demonstrable live: decide a case, then run a similar simulation and watch the
new case appear in `precedent_search` results in the trace panel. Budget one demo beat for
it (§15, beat 7).

### 7.5 Retrieval evaluation

`scripts/03_eval_retrieval.py`: a golden set of 10 queries mapped to expected policy IDs,
reporting **recall@3** and mean score. Run it after seeding, print the number, commit the
output to `docs/`.

Purpose: when the panel asks "how do you know the retrieval isn't hallucinating?", the
answer is a measured number, not an opinion. Threshold to consider healthy: recall@3 ≥ 0.8.
If it is below that, the fix is chunking, not more prompt engineering.

---

## 8. Domain logic (pure Python, no LLM)

`backend/app/domain/calculator.py` — deterministic, unit-tested, zero dependencies on
LangChain.

| Function | Formula / method |
|---|---|
| `pmt(pv, monthly_rate, n)` | Tabela Price: `PV · i / (1 − (1+i)^−n)` |
| `ltv(financed, asset_value)` | `financed / asset_value` |
| `dti(monthly_payment, net_income, existing_debt)` | `(payment + existing_debt) / net_income` |
| `cet_annual(...)` | IRR of the full cash flow (principal, instalments, MIP/DFI insurance, appraisal fee, IOF) via bisection |
| `annual_rate(product, ltv, score)` | Base rate + spread from the policy table |
| `schedule_preview(...)` | First 2 and last 1 amortisation rows |

`backend/app/domain/rules.py` — the decision matrix. Deterministic, mirrors the seeded
policies, returns `Decision` with populated `policy_refs` and `breached_rules`.

Reference thresholds (encoded in both the policy corpus and `rules.py` — they must agree):

- `age_at_maturity = current_age_years + term_months / 12` (the "idade + prazo ≤ 80 anos" rule).
- Auto-approval requires **all of**: LTV ≤ 0.70 · DTI ≤ 0.30 · internal score ≥ 700 ·
  `age_at_maturity` ≤ 80 · income verified.
- Manual review: LTV ≤ 0.80 · DTI ≤ 0.40 · score ≥ 600 · `age_at_maturity` ≤ 80.
- Denial: anything beyond manual-review bounds, or a hard legal block.

`dti` includes pre-existing debt: `(monthly_payment + existing_monthly_debt) / net_monthly`.

> **Consistency invariant.** `rules.py` and the `credit_policies` corpus encode the same
> thresholds. A test (`tests/test_policy_consistency.py`) asserts that every threshold in
> `rules.py` appears in at least one policy document. If the agent cites POL-014 for a rule
> the code does not implement, the demo's credibility collapses under the first follow-up
> question.

---

## 9. API design (FastAPI)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/applications` | Mariana's form → create application + thread, return `application_id` |
| `POST` | `/api/chat` | **SSE.** Body `{thread_id, persona, message}`. Streams trace + tokens. |
| `GET` | `/api/applications?status=manual_review` | Carlos's queue |
| `GET` | `/api/applications/{id}` | Case detail + latest assessment |
| `POST` | `/api/approve` | Resume the `interrupt()` with `Command(resume={...})` |
| `GET` | `/api/trace/{thread_id}` | Historical trace from `decisions_log` |
| `GET` | `/api/health` | Atlas ping + index status |

### 9.1 SSE event contract

Four event types. The frontend must handle all four.

```
event: trace
data: {"node":"policy_retrieval","status":"started","ts":1755180000.12}

event: trace
data: {"node":"policy_retrieval","status":"finished","ms":812,
       "detail":{"op":"$vectorSearch","collection":"credit_policies","k":4,
                 "hits":[{"id":"POL-014","score":0.83,"title":"Limite de LTV..."}]}}

event: token
data: {"text":"Com entrada de 30%"}

event: state
data: {"stage":"negotiation","calc":{...},"decision":{...},"pending_approval":null}

event: done
data: {"thread_id":"APP-20260814-0001"}
```

### 9.2 How the events are produced

```python
async for mode, chunk in graph.astream(
    payload,
    config={"configurable": {"thread_id": thread_id}},
    stream_mode=["updates", "messages", "custom"],
):
    ...
```

- `updates` → node boundaries → `trace` events with `status: started/finished`.
- `messages` → LLM tokens → `token` events.
- `custom` → rich detail (which policy IDs matched, at what score) emitted from inside
  nodes via `get_stream_writer()`.

A `state` event is emitted **once, immediately before `done`**, carrying the final
`stage` / `calc` / `decision` / `pending_approval`. Emitting it per node would make the UI
flicker through intermediate states that were never real conclusions.

```python
from langgraph.config import get_stream_writer

def policy_retrieval(state: AgentState) -> dict:
    writer = get_stream_writer()
    writer({"op": "$vectorSearch", "collection": "credit_policies", "k": 4})
    docs = vector_store.similarity_search(query, k=4, pre_filter={"product": product})
    writer({"hits": [{"id": d.metadata["_id"], "score": d.metadata.get("score")} for d in docs]})
    return {"policies": [d.metadata | {"text": d.page_content} for d in docs]}
```

> **Why `astream` and not `stream_events(version="v3")`.** The trace panel needs *node
> boundaries*, which `stream_mode="updates"` gives directly. `stream_events` is available
> (and `version="v3"` is real — verified), but adds a projection layer we do not need.
> If any code does use `stream_events`, it **must** pass `version="v3"` explicitly; the
> default is still `"v2"` and pre-2026 training data will produce the v2 shape.

### 9.3 The trace panel must be true

Every trace event originates from actual graph execution. No simulated timings, no
hardcoded step lists, no `setTimeout` animations. If a node is skipped, the panel shows it
skipped. The panel's entire value in the interview is that it is *evidence*, and a panel
that lies is worse than no panel — an interviewer who catches one fabricated step
discounts everything else on screen.

---

## 10. Frontend design (Next.js)

One app, two routes, shared components.

```
frontend/
├── app/
│   ├── page.tsx            /          Mariana: simulation form + chat + collapsed trace
│   ├── console/page.tsx    /console   Carlos: queue + case detail + chat + prominent trace
│   └── layout.tsx                     persona switcher in the header
├── components/
│   ├── TracePanel.tsx                 shared, live
│   ├── ChatThread.tsx
│   ├── ScenarioTable.tsx              accumulated negotiation scenarios
│   ├── CaseQueue.tsx
│   └── DecisionCard.tsx               outcome + reasons + policy citations
├── hooks/useAgentStream.ts            SSE consumption
└── lib/api.ts
```

> **Implementation gotcha — do not use `EventSource`.** `EventSource` only issues GET
> requests, and `/api/chat` is a POST with a JSON body. Use `fetch()` with a
> `ReadableStream` reader and parse SSE frames manually (split on `\n\n`, then on
> `event:` / `data:` lines). This is the single most likely place for an executing model to
> produce code that looks right and does not work.

Styling: Tailwind. No component library required. The trace panel is the visual centrepiece
— monospace, colour-coded by node type (deterministic / LLM / vector search / memory
write), with elapsed milliseconds per node.

**Degradation guarantee.** The backend must remain fully demonstrable without the
frontend: `curl -N -X POST localhost:8000/api/chat -d '{...}'` streams the same events. If
the frontend breaks minutes before the presentation, the technical content is still fully
deliverable from a terminal. Include the exact `curl` commands in `docs/demo-script.md`.

---

## 11. Verified API contract

Every signature below was obtained by introspecting the installed package on 2026-08-10,
not from documentation. **Trust this section over memory.**

### 11.1 Pinned versions

```
langgraph==1.2.10
langgraph-checkpoint==4.2.0
langgraph-checkpoint-mongodb==0.4.0
langgraph-store-mongodb==0.3.0
langchain-mongodb==0.11.0
langchain-voyageai==0.4.0
langchain-openai==1.4.3
langchain-core==1.5.3
pymongo==4.16.0
```

### 11.2 Checkpointer

```python
from langgraph.checkpoint.mongodb import MongoDBSaver

MongoDBSaver(
    client: MongoClient,
    db_name: str = "checkpointing_db",
    checkpoint_collection_name: str = "checkpoints",
    writes_collection_name: str = "checkpoint_writes",
    ttl: int | None = None,
    serde: SerializerProtocol | None = None,
    **kwargs,
) -> None

MongoDBSaver.from_conn_string(
    conn_string=None, db_name="checkpointing_db",
    checkpoint_collection_name="checkpoints",
    writes_collection_name="checkpoint_writes",
    ttl=None, **kwargs,
) -> Iterator[MongoDBSaver]     # context manager
```

Module exports exactly: `['MongoDBSaver', 'saver', 'utils']`. **There is no `aio`
submodule and no `AsyncMongoDBSaver`.**

### 11.3 Store

```python
from langgraph.store.mongodb import MongoDBStore, VectorIndexConfig, create_vector_index_config

create_vector_index_config(
    dims: int | None,
    embed: Embeddings | Callable | str,
    fields: list[str] | None = None,
    name: str = "vector_index",
    relevance_score_fn: Literal["euclidean", "cosine", "dotProduct", None] = "cosine",
    embedding_key: str | None = "embedding",
    filters: list[str] | None = None,
) -> VectorIndexConfig

MongoDBStore(
    collection: Collection,
    ttl_config: TTLConfig | None = None,
    index_config: VectorIndexConfig | None = None,
    auto_index_timeout: int = 15,
    query_model: str | None = None,
    **kwargs,
)

MongoDBStore.from_conn_string(
    conn_string=None, db_name="checkpointing_db",
    collection_name="persistent-store",
    ttl_config=None, index_config=None, **kwargs,
) -> Iterator[MongoDBStore]     # context manager

store.put(namespace: tuple[str, ...], key: str, value: dict,
          index: Literal[False] | list[str] | None = None, *, ttl: float | None = ...) -> None
store.get(namespace: tuple[str, ...], key: str, *, refresh_ttl: bool | None = None) -> Item | None
store.search(namespace_prefix: tuple[str, ...], /, *, query: str | None = None,
             filter: dict | None = None, limit: int = 10, offset: int = 0,
             refresh_ttl: bool | None = None, **kwargs) -> list[SearchItem]
```

`TTLConfig` keys: `refresh_on_read`, `omit_expired`, `default_ttl`, `sweep_interval_minutes`.

**No `rerank_config` parameter exists** in 0.3.0.

### 11.4 Vector store

```python
from langchain_mongodb import MongoDBAtlasVectorSearch

MongoDBAtlasVectorSearch(
    collection: Collection,
    embedding: Embeddings,
    index_name: str = "vector_index",
    text_key: str | list[str] = "text",
    embedding_key: str | None = "embedding",
    relevance_score_fn: str | None = "cosine",
    dimensions: int = -1,
    auto_create_index: bool | None = None,
    auto_index_timeout: int = 15,
    vector_index_options: dict | None = None,
    **kwargs,
)

MongoDBAtlasVectorSearch.from_connection_string(
    connection_string: str, namespace: str, embedding: Embeddings, **kwargs
) -> MongoDBAtlasVectorSearch          # namespace is "db.collection"

.create_vector_search_index(
    dimensions: int,
    filters: list[str] | None = None,
    update: bool = False,
    wait_until_complete: float | None = None,
    vector_index_options: dict | None = None,
    **kwargs,
) -> None

.similarity_search(
    query: str, k: int = 4,
    pre_filter: dict | None = None,          # <-- pre_filter, NOT filter
    post_filter_pipeline: list[dict] | None = None,
    oversampling_factor: int = 10,
    include_scores: bool = False,
    include_embeddings: bool = False,
    **kwargs,
) -> list[Document]
```

Use `create_vector_search_index(dimensions=1024, filters=["product","policy_type"],
wait_until_complete=120)` in `scripts/01_create_indexes.py` — it handles index creation
*and* readiness polling, avoiding hand-rolled `list_search_indexes` status checks whose
field name (`status` vs `queryable`) varies across documentation.

`langchain_mongodb` top-level exports: `MongoDBAtlasSemanticCache`,
`MongoDBAtlasVectorSearch`, `MongoDBCache`, `MongoDBChatMessageHistory`.

`langchain_mongodb.retrievers` exports: `MongoDBAtlasFullTextSearchRetriever`,
`MongoDBAtlasHybridSearchRetriever`, `MongoDBAtlasParentDocumentRetriever`,
`MongoDBAtlasSelfQueryRetriever`, `MongoDBGraphRAGRetriever`. (Not used in the build —
worth knowing for Q&A about what else Atlas offers.)

### 11.5 LangGraph

```python
StateGraph.compile(
    checkpointer: Checkpointer = None, *, cache=None, store: BaseStore | None = None,
    interrupt_before=None, interrupt_after=None, debug=False, name=None, transformers=None,
) -> CompiledStateGraph

graph.astream(input, config=None, *, context=None,
              stream_mode: StreamMode | Sequence[StreamMode] | None = None,
              print_mode=(), output_keys=None, interrupt_before=None, interrupt_after=None,
              durability=None, control=None, subgraphs=False, debug=...)

graph.stream_events(input, config=None, *, version: Literal["v1","v2","v3"] = "v2", ...)
graph.astream_events(input, config=None, *, version: Literal["v1","v2","v3"] = "v2", ...)

from langgraph.types import interrupt, Command
interrupt(value: Any) -> Any
Command(graph=..., update=..., resume=..., goto=...)      # dataclass fields

from langgraph.config import get_stream_writer, get_store, get_config
from langgraph.prebuilt import create_react_agent
```

### 11.6 Embeddings

```python
from langchain_voyageai import VoyageAIEmbeddings
VoyageAIEmbeddings(model="voyage-4-lite", output_dimension=1024)
# fields: model (required), batch_size, output_dimension, show_progress_bar,
#         truncation, voyage_api_key, base_url

from langchain_openai import OpenAIEmbeddings
OpenAIEmbeddings(model="text-embedding-3-small", dimensions=1024)
```

### 11.7 Index creation via pymongo (reference only)

Prefer `create_vector_search_index` above. This is documented for the case where the index
must be created outside the vector store (e.g. `agent_memories` if `MongoDBStore`'s
auto-index fails):

```python
from pymongo.operations import SearchIndexModel

collection.create_search_index(
    SearchIndexModel(
        definition={"fields": [
            {"type": "vector", "path": "embedding", "numDimensions": 1024, "similarity": "cosine"},
            {"type": "filter", "path": "product"},
        ]},
        name="vector_index",
        type="vectorSearch",
    )
)
```

---

## 12. Repository layout

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
│   ├── specs/2026-08-10-credit-assistant-design.md    ← this file
│   ├── architecture.md
│   ├── diagrams/{graph,data-flow,memory}.mmd
│   ├── objection-bank.md
│   ├── demo-script.md
│   ├── slides-outline.md
│   └── adr/
│       ├── 0001-mongodb-as-single-data-plane.md
│       ├── 0002-hybrid-deterministic-agentic-graph.md
│       ├── 0003-voyage-ai-embeddings.md
│       └── 0004-prose-embeddings-structured-filters.md
├── backend/
│   ├── pyproject.toml              uv, pinned per §11.1
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
├── frontend/                       see §10
└── data/
    ├── policies/*.md               ~30 chunks
    ├── cases/cases.json            ~60 cases
    └── profiles/profiles.json      3–5 customers
```

---

## 13. Testing strategy

Test where tests pay, given a four-day budget.

| Target | Type | Why |
|---|---|---|
| `domain/calculator.py` | Unit, known-value | Financial arithmetic fails silently and destroys credibility |
| `domain/rules.py` | Unit, decision matrix | Every boundary condition of the decision table |
| Policy/code consistency | Unit | Prevents citing a policy the code does not implement (§8) |
| Graph end-to-end | Smoke, fake LLM | Wiring, routing, state transitions — not model output |
| Retrieval | `03_eval_retrieval.py` | recall@3 ≥ 0.8 on a golden set |

**Not tested:** LLM node outputs, prompt quality, frontend. Judged by rehearsal, not
assertions.

---

## 14. Risks and mitigations

| # | Risk | Impact | Mitigation | Deadline |
|---|---|---|---|---|
| 1 | M0 allows fewer search indexes than needed (limit unconfirmed, possibly 3) | Blocks the whole retrieval design | `00_check_atlas.py` probes it first thing. Fallback: `MongoDBStore` without `index_config` → 2 indexes | Day 1, hour 1 |
| 2 | M0 vector search latency makes the live demo feel slow | Demo drags | Measure on Day 1. If p95 > 1.5s, reduce `k`, reduce corpus, or upgrade tier | Day 1 |
| 3 | Venue network fails | Demo dies | Enable Docker Desktop WSL integration and validate the `mongodb/mongodb-atlas-local` compose path as an offline fallback. **Also record a screen capture of a full successful run on Thursday.** | Day 2 / Day 4 |
| 4 | Docker not currently available in this WSL distro | The "reproduce locally" deliverable ships untested | Enable integration Day 1–2. If not enabled by Wednesday, mark the compose file explicitly as untested in the README rather than implying it works | Day 2 |
| 5 | Executing model writes pre-2026 LangGraph APIs (`astream_events(version="v2")`, `AsyncMongoDBSaver`) | Hours lost debugging | §11 is authoritative and must be quoted into every implementation task | Continuous |
| 6 | LLM latency during live negotiation | Awkward silences | Cap `max_tokens`, stream tokens (already in the SSE contract), pre-warm the connection on app start | Day 3 |
| 7 | Voyage free-tier key not obtained in time | Blocks embeddings | Factory already supports OpenAI at the same 1024 dims; switch is one env var + `--reembed` | Day 1 |
| 8 | Scope overrun on the Next.js frontend | Backend unfinished | Frontend is explicitly cuttable (§15). Backend must be `curl`-demonstrable by end of Day 2 | Day 2 |

---

## 15. Schedule and demo script

### 15.1 Build schedule

| Day | Non-negotiable | Cuttable |
|---|---|---|
| **Mon 10** | Atlas M0 up · index limit verified · seed loaded · **`$vectorSearch` returning sensible results** · `03_eval_retrieval.py` passing | — nothing. If this slips, replan Tuesday morning |
| **Tue 11** | Mariana flow end-to-end · FastAPI SSE demonstrable via `curl` · Next.js scaffold | Visual polish |
| **Wed 12** | Carlos flow: precedents, brief, ReAct negotiation, `interrupt`, persist · trace panel wired | 4th tool (Open Finance) |
| **Thu 13** | Docs, diagrams, objection bank, slides · **two full timed rehearsals** · backup recording | Visual polish |
| **Fri 14** | Present | — |

### 15.2 Demo beats (~45–60 min)

Modular by design — each beat is skippable live if time runs short.

| # | Beat | Minutes | Core? |
|---|---|---|---|
| 1 | **Discovery.** Ask the "customer" about their origination pain before showing anything. Do not open a browser yet. | 5–8 | ✅ |
| 2 | Business framing: friction on both sides, cost of manual review | 3 | ✅ |
| 3 | Mariana simulates → auto-approved case. Trace panel visible. | 4 | ✅ |
| 4 | Mariana simulates → falls to manual review. Show `applications` status change. | 3 | ✅ |
| 5 | Carlos opens the case. Brief with recommendation + policy citations + precedents. **Point out: same `thread_id`.** | 5 | ✅ |
| 6 | Negotiation: 3 scenarios (reduce amount → extend term → Open Finance consent). Scenario table accumulates. | 8 | ✅ |
| 7 | **Kill the backend mid-negotiation. Restart. Continue.** | 2 | ✅ |
| 8 | Approve → `interrupt` resumes → `decisions_log` written → new precedent appears in a subsequent similar search | 4 | ✅ |
| 9 | Architecture walkthrough: the graph, the four workloads on one cluster, the memory split | 8 | ✅ |
| 10 | Show `recall@3` from the eval script | 2 | ⬜ |
| 11 | Q&A / objections | remainder | ✅ |

Beat 1 is the one most candidates skip. It is also an explicit scoring criterion.

`docs/demo-script.md` must contain the **literal values** to type in each field, in order,
that produce the intended outcomes — plus the `curl` fallbacks and a "what to say if X
breaks" column.

---

## 16. Objection bank (seed topics)

Full answers go in `docs/objection-bank.md`. Each answer must be anchored in something
actually built, not in a generalisation.

| Objection | Anchor |
|---|---|
| "How does this scale?" | Atlas Search nodes scale independently of the operational workload; `decisions_log` is append-only and shardable by `application_id`; checkpoints expire by TTL. Be honest that M0 is a demo tier. |
| "How do you guarantee explainability?" | `decisions_log` records every scenario including discarded ones, with `policy_refs`, `precedent_refs`, model id and `prompt_version`. Query it live. |
| "Why isn't it fully automatic?" | `await_approval` is a graph node with `interrupt()`. The agent *cannot* write a decision without human resume. Architecture, not policy. |
| "How do you stop it hallucinating numbers?" | The LLM never computes. `recalculate_scenario` calls deterministic Python. Show `calculator.py`. |
| "Isn't this just a workflow with RAG?" | Deliberate hybrid: deterministic where volume and auditability dominate, agentic where ambiguity does. The criterion is cost and auditability, not fashion. |
| "What about LGPD?" | All data synthetic; Open Finance access is consent-gated in the model (`consent_granted`); field-level encryption and Atlas Queryable Encryption are the production path. |
| "Why MongoDB and not Postgres + pgvector + Redis?" | §3 table: four workloads, one data plane, one consistency model, one operational surface. |
| "What if the model provider goes down?" | Deterministic path (intake→calc→decision) degrades to rules-only; the agentic path is the part that fails. Show that the graph structure makes this a node-level, not system-level, failure. |
| "How would this work with our real policy documents?" | Chunking strategy in §7.2 is document-agnostic; the loader is one script. Discuss versioned policies (`effective_from`, `version` fields already modelled). |

---

## 17. Open items

| Item | Owner | Resolve by |
|---|---|---|
| Atlas M0 cluster provisioned, IP allowlist configured, connection string in `.env` | Thiago | Day 1 |
| Voyage AI API key obtained | Thiago | Day 1 |
| M0 search index limit confirmed empirically | `00_check_atlas.py` | Day 1 |
| `MongoDBSaver(ttl=...)` behaviour — native TTL index or client-side sweep? | `00_check_atlas.py` prints `index_information()` | Day 1 |
| Docker Desktop WSL integration enabled | Thiago | Day 2 |
| Exact OpenAI chat model id available on the account (goes into `settings.llm_model` and `decisions_log.model`) | Thiago | Day 1 |
| Confirmed presentation duration | Thiago | before Thursday rehearsal |
