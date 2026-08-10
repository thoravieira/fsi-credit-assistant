# FSI Credit Assistant

Demo for a MongoDB Solutions Architect interview on **2026-08-14**. LangGraph agent for
Brazilian personal credit, with MongoDB Atlas as the single data plane.

## Before writing any code

The design is already decided and lives in `docs/specs/` (18 files, indexed in
`docs/specs/00-overview.md`). **Read only the spec files your task needs** — loading all of
them wastes context and degrades output.

**`docs/specs/13-verified-api-contract.md` is authoritative.** Every signature there was
obtained by introspecting the installed package. Published documentation is stale in several
places. If your instinct disagrees with file 13, file 13 is right. In particular:

- There is **no** `AsyncMongoDBSaver` and no `langgraph.checkpoint.mongodb.aio`.
- `similarity_search` takes `pre_filter=`, not `filter=`.
- `MongoDBStore` uses `index_config=create_vector_index_config(...)`, not `index={"embed":...}`.
- If you call `stream_events`, pass `version="v3"` explicitly.

## Rules

- Pinned dependency versions in `13-verified-api-contract.md` §1. Do not bump them this week.
- Repository language is **English** (code, comments, docs). Demo-facing content — UI copy,
  policy corpus, agent responses, case narratives — is **Portuguese**.
- `domain/` has zero imports from `langchain*` or `langgraph*`. The LLM never computes a number.
- Trace events shown in the UI must come from real graph execution. No simulated timings.
- `.temp/` is never committed.
- Each spec file ends with acceptance criteria. A task is done when they pass, not before.

## Commands

```
make setup   make seed   make dev   make test   make eval   make demo-reset
```
