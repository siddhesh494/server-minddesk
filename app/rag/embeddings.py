"""Reusable embedding provider. One client is created per application lifetime."""

from __future__ import annotations

from typing import Protocol

from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class EmbeddingProvider(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


def create_embedding_provider(settings: Settings) -> EmbeddingProvider:
    """Document embeddings use RETRIEVAL_DOCUMENT; queries use RETRIEVAL_QUERY."""
    provider = GoogleGenerativeAIEmbeddings(
        model=settings.embedding_model,
        google_api_key=settings.google_api_key or None,
        output_dimensionality=settings.embedding_dimension,
    )
    logger.info(
        "embeddings_initialized",
        model=settings.embedding_model,
        dimension=settings.embedding_dimension,
    )
    return provider
