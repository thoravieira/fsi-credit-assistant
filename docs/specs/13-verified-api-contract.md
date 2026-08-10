# SDD 13 — Verified API contract

> Part of the [FSI Credit Assistant SDD](00-overview.md)
> **This file is authoritative.** Every signature below was obtained by introspecting the
> installed package on **2026-08-10**, not read from documentation.
>
> **If code you are about to write disagrees with this file, this file is right.**
> Published documentation is stale in at least three places, all flagged below with ⚠️.

---

## 1. Pinned versions

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

Pin these exactly in `backend/pyproject.toml`. A minor bump mid-week is not worth the risk
four days before a presentation.

---

## 2. Checkpointer

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

Module exports **exactly**: `['MongoDBSaver', 'saver', 'utils']`.

> ⚠️ **There is no `aio` submodule and no `AsyncMongoDBSaver`.**
> `from langgraph.checkpoint.mongodb.aio import AsyncMongoDBSaver` → `ModuleNotFoundError`.
>
> `MongoDBSaver` implements the async protocol directly: `acopy_thread`,
> `adelete_for_runs`, `adelete_thread`, `aget`, `aget_delta_channel_history`, `aget_tuple`,
> `alist`, `aprune`, `aput`, `aput_writes`. It works with `graph.ainvoke()` and
> `graph.astream()` without modification.

---

## 3. Store

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

> ⚠️ **No `rerank_config` parameter exists** in 0.3.0, contrary to some documentation.
> ⚠️ The API is **not** the `index={"embed": ...}` dict used by `InMemoryStore`. It is
> `index_config=` built via `create_vector_index_config(...)`.
> ⚠️ `db_name` defaults to `"checkpointing_db"` — always pass it explicitly.

---

## 4. Vector store

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

> ⚠️ The filter parameter is **`pre_filter`**, not `filter`.

Use `create_vector_search_index(dimensions=1024, filters=[...], wait_until_complete=120)` —
it creates the index *and* polls until queryable, avoiding a hand-rolled
`list_search_indexes` status loop whose field name (`status` vs `queryable`) varies across
documentation versions.

`langchain_mongodb` top-level exports: `MongoDBAtlasSemanticCache`,
`MongoDBAtlasVectorSearch`, `MongoDBCache`, `MongoDBChatMessageHistory`.

`langchain_mongodb.retrievers` exports: `MongoDBAtlasFullTextSearchRetriever`,
`MongoDBAtlasHybridSearchRetriever`, `MongoDBAtlasParentDocumentRetriever`,
`MongoDBAtlasSelfQueryRetriever`, `MongoDBGraphRAGRetriever`.

None of the retrievers are used in this build — worth knowing for Q&A about what else Atlas
offers out of the box.

---

## 5. LangGraph

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

> ⚠️ `version` defaults to `"v2"`. LangGraph 1.2 introduced the typed v3 projection
> (`stream.messages`, `stream.output`, `stream.interrupts`). Pre-2026 training data produces
> v2 code silently. **If you call `stream_events` at all, pass `version="v3"` explicitly.**
> This design uses `astream` instead — see [11 §3](11-api-sse.md).

---

## 6. Embeddings

```python
from langchain_voyageai import VoyageAIEmbeddings
VoyageAIEmbeddings(model="voyage-4-lite", output_dimension=1024)
# fields: model (required), batch_size, output_dimension, show_progress_bar,
#         truncation, voyage_api_key, base_url

from langchain_openai import OpenAIEmbeddings
OpenAIEmbeddings(model="text-embedding-3-small", dimensions=1024)
```

Voyage `voyage-4` family, January 2026: `voyage-4-lite` ($0.02/1M), `voyage-4` ($0.06/1M),
`voyage-4-large` ($0.12/1M), `voyage-context-4` ($0.12/1M). Matryoshka dimensions
256/512/1024/2048, 32K context. Free tier: 200M tokens.

Note the parameter names differ: `output_dimension` (Voyage) vs `dimensions` (OpenAI).

---

## 7. Low-level index creation (reference only)

Prefer `create_vector_search_index` from §4. This is documented for the case where an index
must be created outside a vector store — e.g. `agent_memories` if `MongoDBStore`'s
auto-index fails.

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

## Summary of stale-documentation traps

| Trap | Reality |
|---|---|
| `AsyncMongoDBSaver` / `langgraph.checkpoint.mongodb.aio` | Does not exist. Use `MongoDBSaver`. |
| `MongoDBStore(rerank_config=...)` | Does not exist in 0.3.0. |
| `index={"embed": ...}` on `MongoDBStore` | Wrong API. Use `index_config=create_vector_index_config(...)`. |
| `similarity_search(..., filter=...)` | It is `pre_filter=`. |
| `astream_events(..., version="v2")` | Default, but v3 is current. Pass it explicitly or use `astream`. |
| Motor as the async MongoDB driver | EOL 2026-05-14. PyMongo's native `AsyncMongoClient` is the path. |
