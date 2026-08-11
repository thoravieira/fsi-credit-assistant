# SDD 16 — Demo plan

> Part of the [FSI Credit Assistant SDD](00-overview.md)
> **Produces:** `docs/demo-script.md`, `docs/slides-outline.md`
> **Presentation:** Friday 2026-08-14, 45–60 min + Q&A

---

## 1. Build schedule

| Day | Non-negotiable | Cuttable |
|---|---|---|
| **Mon 10** | Atlas M0 up · index limit verified · seed loaded · **`$vectorSearch` returning sensible results** · `03_eval_retrieval.py` passing | — nothing. If this slips, replan Tuesday morning |
| **Tue 11** | Mariana flow end-to-end · FastAPI SSE demonstrable via `curl` · Next.js scaffold | Visual polish |
| **Wed 12** | Carlos flow: precedents, brief, ReAct negotiation, `interrupt`, persist · trace panel wired | 4th tool (`check_open_finance_assets`) |
| **Thu 13** | Docs, diagrams, objection bank, slides · **two full timed rehearsals** · backup screen recording | Visual polish |
| **Fri 14** | Present | — |

**The Monday goal is not "start building" — it is "prove the riskiest assumption".** If
`$vectorSearch` on M0 does not return sensible results against the seeded corpus by Monday
night, the design changes on Tuesday, not on Thursday.

---

## 2. Demo beats

Modular by design — each beat is skippable live if time runs short.

| # | Beat | Min | Core |
|---|---|---|---|
| 1 | **Discovery.** Ask the "customer" about their origination pain before showing anything. Do not open a browser yet. | 5–8 | ✅ |
| 2 | Business framing: friction on both sides, cost of manual review | 3 | ✅ |
| 3 | Mariana simulates → auto-approved. Imóvel R$ 400 mil, entrada R$ 180 mil, 360 meses. Trace panel visible. | 4 | ✅ |
| 4 | Mariana drops the entrada to R$ 100 mil → falls to manual review. Show the `applications` status change. | 3 | ✅ |
| 5 | Carlos opens the case. Brief with recommendation + policy citations + precedents. **Say the words "same thread ID".** | 5 | ✅ |
| 6 | Negotiation: 3 scenarios — reduce amount → extend term → Open Finance consent. `ScenarioTable` accumulates. | 8 | ✅ |
| 7 | **Kill the backend mid-negotiation. Restart. Continue.** | 2 | ✅ |
| 8 | Approve → `interrupt` resumes → `decisions_log` written → the new precedent appears in a subsequent similar search | 4 | ✅ |
| 9 | Architecture walkthrough: the graph, four workloads on one cluster, the memory split | 8 | ✅ |
| 10 | Show `recall@3` from the eval script | 2 | ⬜ |
| 11 | Q&A / objections | rest | ✅ |

Core total: ~42–45 min plus Q&A. Fits the 45–60 window with beat 10 as the release valve.

### Beat 1 is the one that separates candidates

Most technically strong candidates skip discovery and go straight to the screen. It is an
explicitly scored criterion. Prepare four questions to ask the "customer" — about volume of
manual reviews, average turnaround, what analysts complain about, what happens when a case
is declined — and *actually listen*, then reference their answers during the demo.

### The beat 3 / beat 4 figures are load-bearing — do not round them

Both run against **CUST-0001** (Mariana Duarte: renda líquida R$ 11.200, dívida mensal
existente R$ 1.350, score interno 782), and the outcome of each is arithmetic, not
narrative. Verified against the seeded profile:

| | Beat 3 | Beat 4 |
|---|---|---|
| Imóvel / entrada | R$ 400.000 / R$ 180.000 | R$ 400.000 / R$ 100.000 |
| Financiado | R$ 220.000 | R$ 300.000 |
| LTV · DTI | 55% · 28,4% | 75% · 35,8% |
| Parcela · taxa · CET | R$ 1.831,54 · 9,8% · 10,37% | R$ 2.658,78 · 10,6% · 11,13% |
| Outcome | `auto_approved` | `manual_review` |
| Citations | POL-020, POL-004, POL-008, POL-012, POL-006 | POL-020, POL-004 |

**Beat 4 changes the entrada, not the asset.** Same imóvel on the same thread, so it
exercises the re-simulation path — `intake` patches `down_payment` on the prior application
and the financed amount, LTV and decision all move with it. That is the *"e se eu desse mais
entrada?"* interaction, and running beat 4 as a fresh application instead would skip the one
thing beat 3 → beat 4 is there to show.

An earlier draft used R$ 560.000 / R$ 112.000 (financiado R$ 448.000). **That combination is
denied, not manual review**: DTI lands at 47,5%, past POL-004's absolute 40% ceiling
("reprovadas automaticamente"). Beat 5 needs `manual_review` to put the case in Carlos's
queue, so a denial breaks every beat after it. R$ 448.000 survives in
`tests/test_calculator.py` as the pinned PMT reference value ([10](10-domain-credit.md)
acceptance) and in the denial test — those are correct and should stay.

### Beat 6 ordering

End the sequence on the Open Finance lever. The first two scenarios move the case on
*numbers*; the third moves it on a *business* mechanism. That is the strongest moment
available and it should not be buried in the middle.

### Beat 7 rehearsal

This is the beat most likely to expose an accidental in-memory cache. Rehearse it
specifically, twice, on Thursday. Precondition in [07 §3](07-memory.md).

---

## 3. `docs/demo-script.md` requirements

Not a summary — an operating manual. It must contain:

- The **literal values** to type in each field, in order, that produce each intended
  outcome. Amounts, terms, down payments, exact phrasings for Carlos's messages.
- The `curl` fallback commands from [11](11-api-sse.md).
- A "what to say if X breaks" column for each beat.
- The reset procedure (`make demo-reset`) and how long it takes.
- Timing checkpoints: where you should be at minute 15, 30, 45.

Rehearse with this document open on a second screen, twice on Thursday, timed.

---

## 4. `docs/slides-outline.md`

Content per slide; the deck itself gets built in your own tool. Slides support beats 1, 2
and 9 only — the rest is live product. Suggested spine:

1. Title + who you are
2. The problem, in the customer's words (fill in after discovery)
3. Cost of the status quo: manual review turnaround, analyst rework
4. What we built, in one sentence
5. *(switch to live demo)*
6. Architecture: the graph
7. Architecture: four workloads, one data plane
8. Architecture: short-term vs long-term memory
9. What I would do next in production (auth, `Decimal`, hybrid search, scale)
10. Q&A

Slide 9 matters. Volunteering the production gaps before the panel finds them converts a
weakness into evidence of judgement.

---

## Acceptance criteria

- [ ] `docs/demo-script.md` exists with literal input values for all 11 beats.
- [ ] `docs/slides-outline.md` exists.
- [ ] Two full timed rehearsals completed on Thursday.
- [ ] Beat 7 rehearsed at least twice.
- [ ] A screen recording of a complete successful run is saved locally.
- [ ] `make demo-reset` verified between rehearsals.
- [ ] Four discovery questions written down for beat 1.
