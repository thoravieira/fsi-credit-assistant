# SDD 17 — Objection bank

> Part of the [FSI Credit Assistant SDD](00-overview.md)
> **Produces:** `docs/objection-bank.md`
> **Why this is a first-class deliverable:** "how you handle live objections" is an explicit
> scoring criterion. The panel role-plays the customer and analyst.

---

## The rule for every answer

**Anchor it in something you actually built.** A general answer about explainability is
worth little; opening `decisions_log` and running a query is worth a lot. Each row below
names its anchor.

| Objection | Anchor |
|---|---|
| *"How does this scale?"* | Atlas Search nodes scale independently of the operational workload. `decisions_log` is append-only and shardable by `application_id`. Checkpoints expire by TTL, so agent state does not grow without bound. **Be honest that M0 is a demo tier** — volunteering that is stronger than being caught. |
| *"How do you guarantee explainability?"* | `decisions_log` records every scenario **including discarded ones**, with `policy_refs`, `precedent_refs`, model id and `prompt_version`. Query it live in front of them. [02 §6](02-data-model.md) |
| *"Why isn't it fully automatic?"* | `await_approval` is a graph node calling `interrupt()`. The agent **cannot** write a decision without a human resume. Architecture, not policy — and visible as a paused step in the trace panel. [06 §4](06-negotiation-agent.md) |
| *"How do you stop it hallucinating numbers?"* | The LLM never computes. `recalculate_scenario` calls deterministic Python. Open `calculator.py` on screen. [10](10-domain-credit.md) |
| *"Isn't this just a workflow with RAG?"* | Deliberate hybrid: deterministic where volume and auditability dominate, agentic where ambiguity does. **The criterion is cost and auditability, not fashion.** [06 §1](06-negotiation-agent.md) |
| *"How do you know the retrieval is any good?"* | recall@3 measured on a golden set, output committed to the repo. Quote the number. [09](09-retrieval-eval.md) |
| *"What about LGPD?"* | All data synthetic. Open Finance access is consent-gated in the model (`consent_granted`). Field-level encryption and Atlas Queryable Encryption are the production path. Known gap: no auth in the demo — say so first. |
| *"Why MongoDB and not Postgres + pgvector + Redis + a vector DB?"* | Four workloads, one data plane, one consistency model, one driver, one backup policy, one security review. [01 §2](01-architecture.md) |
| *"What if the model provider goes down?"* | The deterministic path (intake → calculator → decision) degrades to rules-only output; only the agentic path fails. The graph structure makes this a **node-level**, not system-level, failure. [01 §4](01-architecture.md) |
| *"How would this work with our real policy documents?"* | The chunking strategy in [08 §2](08-retrieval.md) is document-agnostic; the loader is one script. Policies are already modelled with `effective_from` and `version`, so versioned policy sets are a data concern, not a redesign. |
| *"What does this cost to run?"* | Embeddings are effectively free at this corpus size (200M-token Voyage free tier vs ~50k tokens used). The real cost is LLM inference on the negotiation path only — which is exactly why the high-volume path is deterministic. |

---

## Objections you should raise yourself

Volunteering a limitation before it is found reads as judgement. Working these into slide 9
([16 §4](16-demo-plan.md)) is worth more than defending them under questioning:

- No authentication or RBAC — persona switching is a UI toggle.
- Money is `float`, not `Decimal` or integer cents.
- M0 free tier; no performance benchmarking done.
- Policy corpus is synthetic and small (~30 chunks).
- No human evaluation of the agent's negotiation quality — only retrieval was measured.

---

## Acceptance criteria

- [ ] `docs/objection-bank.md` written with a full answer per row, not just the anchor.
- [ ] Each answer is under 60 seconds spoken.
- [ ] The five self-raised limitations are on slide 9.
- [ ] The `decisions_log` query that demonstrates explainability is written down and tested
      — do not compose it live.
- [ ] The recall@3 number is memorised.
