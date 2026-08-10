# SDD 12 — Frontend

> Part of the [FSI Credit Assistant SDD](00-overview.md)
> **Reads:** [11 API and SSE](11-api-sse.md)
> **Implemented by:** `frontend/`
> **Model:** Sonnet
> **Scope valve:** this is the cuttable deliverable. See [16](16-demo-plan.md).

---

## 1. Structure

**One Next.js app, two routes, shared components.** Not two apps — that would roughly double
the work for no narrative gain, since the personas share the backend, the SSE hook and the
trace panel.

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

Styling: Tailwind. No component library required.

---

## 2. ⚠️ Do not use `EventSource`

`EventSource` only issues **GET** requests. `/api/chat` is a POST with a JSON body.

Use `fetch()` with a `ReadableStream` reader and parse SSE frames manually: split the
decoded buffer on `\n\n`, then parse each frame's `event:` and `data:` lines. Keep a
trailing-partial-frame buffer across reads — chunks do not align to frame boundaries.

**This is the single most likely place for the executing model to produce code that looks
correct and does not work.** It will reach for `new EventSource('/api/chat')` because that
is what the training data contains.

---

## 3. The trace panel

The visual centrepiece. Monospace, colour-coded by node type, elapsed milliseconds per node:

| Node type | Examples | Colour role |
|---|---|---|
| Deterministic | `router`, `credit_calculator`, `decision` | neutral |
| LLM | `intake`, `analyst_brief`, `customer_response` | accent |
| Vector search | `policy_retrieval`, `precedent_search` | highlight — this is the MongoDB moment |
| Memory | `load_context`, `persist_decision` | secondary highlight |

Vector search and memory steps should be the ones the eye lands on. That is the demo's
argument, rendered.

Expandable detail per step: matched policy IDs with scores, the actual query text, the
namespace written to. When Carlos asks "why did it say that?", the answer is one click away
on screen.

Collapsed by default on `/` (Mariana does not care), expanded by default on `/console`.

---

## 4. `DecisionCard`

Shows outcome, `reasons` (Portuguese), and `policy_refs` rendered as clickable chips that
expand the cited policy text. Clicking POL-014 and showing the actual policy language is a
five-second answer to any explainability question from the floor.

---

## Acceptance criteria

- [ ] One Next.js app, two routes, one `useAgentStream` hook shared by both.
- [ ] SSE consumed via `fetch` + `ReadableStream` — **zero occurrences of `EventSource`**.
- [ ] Partial SSE frames spanning chunk boundaries are handled (test with a slow response).
- [ ] Trace steps appear **as they happen**, not batched at the end.
- [ ] Node timings shown come from the backend, not measured in the browser.
- [ ] `ScenarioTable` accumulates across negotiation turns without a page reload.
- [ ] `policy_refs` chips expand to real policy text.
- [ ] The app is legible on a projector: test at 1280×720 and from three metres away.
