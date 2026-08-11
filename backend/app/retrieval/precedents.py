"""SDD 08 §3 — precedent retrieval, filtered by product and optionally `ltv_band`."""

from functools import lru_cache

from langchain_core.documents import Document
from langchain_mongodb import MongoDBAtlasVectorSearch

from app.db import get_db
from app.embeddings import get_embeddings

INDEX_NAME = "vector_index"


@lru_cache
def _vector_store() -> MongoDBAtlasVectorSearch:
    return MongoDBAtlasVectorSearch(
        collection=get_db()["historical_cases"],
        embedding=get_embeddings(),
        index_name=INDEX_NAME,
        # `historical_cases` stores its prose in `summary`, and that is the
        # field `02_seed.py` embeds (SDD 02 §4). The default `text_key="text"`
        # matches `credit_policies` but not this collection: it returns hits
        # whose `page_content` is empty, which is invisible in an id-based
        # recall metric and very visible on stage.
        text_key="summary",
    )


def search_precedents(
    query: str, product: str, ltv_band: str | None = None, k: int = 3
) -> list[Document]:
    pre_filter = {"product": product}
    if ltv_band is not None:
        pre_filter["ltv_band"] = ltv_band
    return _vector_store().similarity_search(
        query, k=k, pre_filter=pre_filter, include_scores=True
    )
