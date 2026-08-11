# SDD 10 — Credit domain

> Part of the [FSI Credit Assistant SDD](00-overview.md)
> **Reads:** [02 Data model](02-data-model.md)
> **Feeds:** [05 Nodes](05-graph-nodes-and-routing.md), [06 Negotiation](06-negotiation-agent.md)
> **Implemented by:** `backend/app/domain/calculator.py`, `backend/app/domain/rules.py`
> **Model:** Sonnet for `calculator.py`, **[OPUS]** for `rules.py`
> **Zero LLM involvement. Zero LangChain imports. Fully unit-tested.**

---

## 1. Why this file is load-bearing

This is what separates a credit demo from a chatbot that invents numbers. Every figure on
screen during the presentation comes from here. If the arithmetic is wrong, the first
domain-literate question destroys the demo — and the panel is simulating bank staff.

It is also the reason the negotiation agent can be trusted: the model chooses the scenario,
this module evaluates it.

---

## 2. `calculator.py`

| Function | Formula / method |
|---|---|
| `pmt(pv, monthly_rate, n)` | Tabela Price: `PV · i / (1 − (1+i)^−n)` |
| `ltv(financed, asset_value)` | `financed / asset_value` |
| `dti(monthly_payment, net_income, existing_debt)` | `(payment + existing_debt) / net_income` |
| `cet_annual(...)` | IRR of the full cash flow (principal, instalments, MIP/DFI insurance, appraisal fee, IOF) via bisection |
| `annual_rate(product, ltv, score)` | Base rate + spread from the policy table |
| `schedule_preview(...)` | First 2 and last 1 amortisation rows |

Notes for implementation:

- `monthly_rate` from an annual rate is `(1 + annual)**(1/12) - 1` — **effective**
  conversion, not `annual / 12`. Getting this wrong is the single most common error in
  Brazilian credit code and produces numbers a bank employee will spot immediately.
- `cet_annual` by bisection over a bracketed range (e.g. 0 to 2.0 annual) converging to
  1e-7. Do not use Newton's method — it can diverge on irregular cash flows and there is no
  reason to risk it here.
- All money values are `float` in this demo. State explicitly in the README that production
  would use `Decimal` or integer cents. Volunteering that limitation reads as maturity;
  being caught on it does not.

---

## 3. `rules.py` — the decision matrix **[OPUS]**

Deterministic. Mirrors the seeded policies. Returns a `Decision` with populated
`policy_refs` and `breached_rules` ([04 §2](04-graph-state.md)).

`age_at_maturity = current_age_years + term_months / 12` — the "idade + prazo ≤ 80 anos"
rule.

`dti` includes pre-existing debt:
`(monthly_payment + existing_monthly_debt) / net_monthly`.

### Thresholds are per product

The corpus seeded in Day 1 sets **different limits for `mortgage` and `auto`**, so the
matrix is a table per product, not one shared grid. Every threshold below carries the policy
that states it; §4 asserts the correspondence.

| Rule id | `mortgage` | `auto` |
|---|---|---|
| `ltv_auto_approval_limit` | ≤ 0.70 · POL-020 | ≤ 0.80 · POL-021 |
| `dti_auto_approval_limit` | ≤ 0.30 · POL-004 | ≤ 0.35 · POL-005 |
| `score_auto_approval_floor` | ≥ 750 · POL-008 | ≥ 700 · POL-009 |
| `amount_auto_approval_limit` | ≤ R$ 300.000 · POL-020 | ≤ R$ 80.000 · POL-021 |
| `ltv_absolute_limit` | ≤ 0.80 · POL-001 | ≤ 0.80 · POL-003 |
| `dti_absolute_limit` | ≤ 0.40 · POL-004 | ≤ 0.45 · POL-005 |
| `score_absolute_floor` | ≥ 650 · POL-008 | ≥ 600 · POL-009 |
| `age_at_maturity_limit` | ≤ 80 anos · POL-006 | ≤ 80 anos · POL-007 |
| `income_verification` | verified · POL-012 | verified · POL-013 |

### Outcomes

| Outcome | Conditions |
|---|---|
| `denied` | Any `*_absolute_*` or `age_at_maturity_limit` rule breached |
| `auto_approved` | No absolute breach **and** every `*_auto_approval_*` rule satisfied **and** income verified |
| `manual_review` | No absolute breach, but at least one auto-approval rule breached |

`breached_rules` carries the rule ids that produced the outcome: the absolute rules for
`denied`, the auto-approval rules for `manual_review`, and `[]` for `auto_approved`.

Every returned `Decision` must populate `reasons` in Portuguese (they are shown to Mariana
and Carlos) and `policy_refs` with the `POL-xxx` ids that justify the outcome — including on
`auto_approved`, where the citations are the limits the application stayed within. A decision
without citations is not explainable, and explainability is a scored criterion.

### Deliberately not implemented

Two policy families have no input in `AgentState` ([04 §2](04-graph-state.md)) and are out of
scope rather than silently approximated:

- **POL-022 / POL-023 — inventário.** The "hard legal block" is a documental restriction.
  `CreditApplication` carries no property-status field, so no probate check runs. Adding one
  means adding the field first.
- **POL-002 vs POL-003 — veículo novo vs. usado.** `CreditApplication` has no vehicle-age
  field, so `auto` uses POL-003's conservative 0.80 rather than POL-002's 0.90 for new
  vehicles. This under-approves rather than over-approves, which is the correct direction to
  fail.

Both are stated in the README's limitations section. Volunteering them is stronger than
being caught on them.

---

## 4. Policy–code consistency invariant

**`rules.py` and the `credit_policies` corpus encode the same thresholds.**

`tests/test_policy_consistency.py` asserts, for every threshold in the §3 table, that the
value appears **in the specific policy `rules.py` cites** and that the policy's `product`
front-matter matches the product the threshold applies to.

"Appears in at least one policy document" is too weak a check to be worth writing: `700`
appears in POL-009, so a mortgage rule citing a score floor of 700 would pass while every
mortgage score policy on screen says 750 or 650. The assertion has to be per-citation and
per-product or it certifies nothing.

The failure this prevents: the agent cites POL-014 for a rule the code does not implement.
A panel member who reads the cited policy on screen and finds it says 75% while the system
applied 80% will discount everything else you showed. It is a silent, high-consequence
divergence and exactly what a test is for.

---

## Acceptance criteria

- [ ] `pmt()` matches a known reference value: PV 448 000, 0.95% monthly, 360 months →
      verify against an independent calculator and pin the expected value in the test.
- [ ] Monthly rate conversion is effective, not nominal — asserted in a test.
- [ ] `cet_annual` > `annual_rate` for every scenario with fees, always.
- [ ] `dti` includes `existing_monthly_debt`.
- [ ] `rules.py` returns `auto_approved` / `manual_review` / `denied` correctly at every
      boundary value in the §3 table, for **both** products (test each threshold at −0.01,
      exact, +0.01 — the exact value is inside the limit, since every rule is `≤` / `≥`).
- [ ] Every `Decision` has non-empty `reasons` and `policy_refs`, `auto_approved` included.
- [ ] `tests/test_policy_consistency.py` passes.
- [ ] Zero imports from `langchain*` or `langgraph*` in `domain/`.
