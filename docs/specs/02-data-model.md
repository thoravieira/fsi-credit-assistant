# SDD 02 — Data model

> Part of the [FSI Credit Assistant SDD](00-overview.md)
> **Feeds:** [03 Indexes](03-atlas-indexes.md) · [05 Nodes](05-graph-nodes-and-routing.md) · [08 Retrieval](08-retrieval.md)
> **Implemented by:** `backend/scripts/02_seed.py`, `backend/app/db.py`, `data/`
> **Model:** Sonnet

Database: `credit_assistant`.

---

## 1. Collections

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

---

## 2. `customer_profiles`

3–5 documents, seeded from `data/profiles/profiles.json`.

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

**`open_finance.consent_granted` starts as `false` on purpose.** It is the lever Carlos
pulls during negotiation — the moment where a business concept (Open Finance consent)
becomes a visible agent action. Seed at least one profile whose case only clears with the
consent granted.

### Profile casting

Seed profiles that produce the outcomes the demo script needs:

| Profile | Designed outcome | Why |
|---|---|---|
| `CUST-0001` Mariana | Clears automatically at a conservative amount, falls to manual review at the amount she actually wants | Drives beats 3 and 4 |
| `CUST-0002` | Self-employed, DECORE income, high score | Exercises the income-verification policy |
| `CUST-0003` | Hard block (property in probate) | Shows a denial that is *not* about numbers |

---

## 3. `credit_policies`

One document per policy chunk. ~30 documents, authored in `data/policies/*.md`.

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

`text` is the embedded field. Full prose, self-contained, **80–200 words**. A chunk must be
readable on its own when displayed in the trace panel, because it *will* be displayed.

`effective_from` and `version` are modelled but not exercised by the demo. They exist so the
answer to *"how would this work with our real, versioned policy documents?"* points at
fields that are already there.

### Policy families to author (~30 chunks)

LTV limits by product · maximum DTI (comprometimento de renda) · age + term ≤ 80 years ·
minimum score bands · FGTS usage · income verification for self-employed (DECORE) ·
alternative collateral · Open Finance asset sharing as a risk mitigant · rate spread table
by LTV × score · approval authority levels (alçadas) · restrictions on properties in
probate.

> **Consistency invariant.** Every numeric threshold in these documents must match
> `domain/rules.py`. Enforced by a test — see [10 §4](10-domain-credit.md).

---

## 4. `historical_cases`

~60 seeded from `data/cases/cases.json`, then grown live by the agent.

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

**`summary` is the embedded field, and it is prose — never a JSON dump.** The reasoning is
in [08 §2](08-retrieval.md) and it is a talking point, not an implementation preference.

`ltv_band` ∈ `low` (≤ 0.60) · `mid` (0.60–0.75) · `high` (> 0.75). Derived at seed time,
used as a vector-index filter field.

Seed the corpus so that at least three cases are genuinely similar to Mariana's
manual-review scenario. Retrieval that returns nothing relevant on stage is worse than no
retrieval.

---

## 5. `applications`

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
  "latest_assessment": { /* CalcResult + Decision, denormalised for the queue UI */ }
}
```

`status` ∈ `draft` · `auto_approved` · `manual_review` · `approved` ·
`approved_with_conditions` · `denied`.

**`thread_id` equals `_id`.** This is the mechanism by which Mariana and Carlos share one
LangGraph thread — see [04 §1](04-graph-state.md).

`latest_assessment` is denormalised so Carlos's queue renders without touching
`decisions_log`. Written by the `decision` node. Denormalisation here is deliberate: the
queue is read on every poll, the log is append-only and grows without bound.

---

## 6. `decisions_log`

Append-only. Every assessment **and** every discarded negotiation scenario is written here.

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
  "model": "<settings.llm_model>",
  "prompt_version": "v1",
  "created_at": "2026-08-14T13:05:44Z"
}
```

`event_type` ∈ `assessment` · `scenario_simulated` · `recommendation` · `human_approval` ·
`final_decision`.

`actor.type` ∈ `customer` · `analyst` · `agent`.

**Two properties that carry the whole explainability argument:**

1. **Discarded scenarios are recorded.** A regulator does not want the final answer; they
   want the path. The scenarios Carlos rejected are evidence of process.
2. **Every path writes here — including automatic approvals.** The `decision` node writes an
   `assessment` event before the customer sees any answer. An audit trail that only covers
   the cases a human touched is not an audit trail.

`model` and `prompt_version` make prompt provenance part of the audit record. When asked
*"how do you know which version of the system made this decision?"*, the answer is a field.

---

## Acceptance criteria

- [ ] `data/policies/` contains ~30 chunks, each 80–200 words, spanning all listed families.
- [ ] `data/cases/cases.json` contains ~60 cases, each with a prose `summary`.
- [ ] At least 3 seeded cases are genuinely similar to Mariana's manual-review scenario.
- [ ] `data/profiles/profiles.json` contains the 3 cast profiles above.
- [ ] `scripts/02_seed.py` is idempotent — running it twice leaves the same document count.
- [ ] `scripts/02_seed.py --reembed` regenerates embeddings without re-authoring content.
- [ ] Every numeric threshold in `data/policies/` matches `domain/rules.py`
      (`tests/test_policy_consistency.py` passes).
