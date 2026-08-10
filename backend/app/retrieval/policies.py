"""SDD 08 §3 — policy retrieval. `pre_filter`, never post-filtering (SDD 13 §4)."""

from functools import lru_cache

from langchain_core.documents import Document
from langchain_mongodb import MongoDBAtlasVectorSearch

from app.db import get_db
from app.embeddings import get_embeddings

INDEX_NAME = "vector_index"


@lru_cache
def _vector_store() -> MongoDBAtlasVectorSearch:
    return MongoDBAtlasVectorSearch(
        collection=get_db()["credit_policies"], embedding=get_embeddings(), index_name=INDEX_NAME
    )


def search_policies(query: str, product: str, k: int = 4) -> list[Document]:
    return _vector_store().similarity_search(
        query, k=k, pre_filter={"product": product}, include_scores=True
    )
