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

| Outcome | Conditions |
|---|---|
| `auto_approved` | **All of:** LTV ≤ 0.70 · DTI ≤ 0.30 · internal score ≥ 700 · `age_at_maturity` ≤ 80 · income verified |
| `manual_review` | LTV ≤ 0.80 · DTI ≤ 0.40 · score ≥ 600 · `age_at_maturity` ≤ 80 |
| `denied` | Anything beyond manual-review bounds, or a hard legal block |

`dti` includes pre-existing debt:
`(monthly_payment + existing_monthly_debt) / net_monthly`.

Every returned `Decision` must populate `reasons` in Portuguese (they are shown to Mariana
and Carlos) and `policy_refs` with the `POL-xxx` ids that justify the outcome. A decision
without citations is not explainable, and explainability is a scored criterion.

---

## 4. Policy–code consistency invariant

**`rules.py` and the `credit_policies` corpus encode the same thresholds.**

`tests/test_policy_consistency.py` asserts that every threshold in `rules.py` appears in at
least one policy document.

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
      boundary value (test each threshold at −0.01, exact, +0.01).
- [ ] Every `Decision` has non-empty `reasons` and `policy_refs`.
- [ ] `tests/test_policy_consistency.py` passes.
- [ ] Zero imports from `langchain*` or `langgraph*` in `domain/`.
