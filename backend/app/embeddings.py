from langchain_core.embeddings import Embeddings

from app.config import get_settings


def get_embeddings() -> Embeddings:
    settings = get_settings()

    if settings.embedding_provider == "voyage":
        from langchain_voyageai import VoyageAIEmbeddings

        return VoyageAIEmbeddings(
            model="voyage-4-lite",
            output_dimension=settings.embedding_dimensions,
            voyage_api_key=settings.voyage_api_key,
        )

    if settings.embedding_provider == "openai":
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            model="text-embedding-3-small",
            dimensions=settings.embedding_dimensions,
            api_key=settings.openai_api_key,
        )

    raise ValueError(f"Unknown EMBEDDING_PROVIDER: {settings.embedding_provider!r}")
