"""Shared Pinecone client. One index is used for every tenant namespace."""

from __future__ import annotations

from typing import Any, Protocol

from pinecone import Pinecone

from app.core.config import Settings
from app.core.exceptions import PineconeError
from app.core.logging import get_logger

logger = get_logger(__name__)


class VectorIndex(Protocol):
    def upsert(self, vectors: list[dict[str, Any]], namespace: str) -> Any: ...

    def query(
        self,
        vector: list[float],
        top_k: int,
        namespace: str,
        include_metadata: bool = True,
    ) -> Any: ...

    def delete(self, *, delete_all: bool = False, namespace: str) -> Any: ...


class PineconeIndexAdapter:
    """Thin adapter so tests can swap a fake index without changing services."""

    def __init__(self, index: Any) -> None:
        self._index = index

    def upsert(self, vectors: list[dict[str, Any]], namespace: str) -> Any:
        return self._index.upsert(vectors=vectors, namespace=namespace)

    def query(
        self,
        vector: list[float],
        top_k: int,
        namespace: str,
        include_metadata: bool = True,
    ) -> Any:
        return self._index.query(
            vector=vector,
            top_k=top_k,
            namespace=namespace,
            include_metadata=include_metadata,
        )

    def delete(self, *, delete_all: bool = False, namespace: str) -> Any:
        # Pinecone-native namespace clear. Do not invent a custom deletion API.
        if hasattr(self._index, "delete_namespace"):
            try:
                return self._index.delete_namespace(namespace=namespace)
            except Exception:
                logger.info("pinecone_delete_namespace_fallback", namespace=namespace)
        return self._index.delete(delete_all=delete_all, namespace=namespace)


def initialize_pinecone(settings: Settings) -> PineconeIndexAdapter:
    client = Pinecone(api_key=settings.pinecone_api_key)
    description = None
    try:
        description = client.describe_index(settings.pinecone_index_name)
    except Exception as exc:
        raise PineconeError(
            f"Pinecone index '{settings.pinecone_index_name}' was not found. "
            "Create one cosine index whose dimension matches EMBEDDING_DIMENSION."
        ) from exc

    dimension = getattr(description, "dimension", None)
    if dimension is None and isinstance(description, dict):
        dimension = description.get("dimension")
    if dimension is not None and int(dimension) != settings.embedding_dimension:
        raise PineconeError(
            f"Pinecone index dimension {dimension} does not match "
            f"EMBEDDING_DIMENSION={settings.embedding_dimension}"
        )

    if settings.pinecone_index_host:
        index = client.Index(host=settings.pinecone_index_host)
    else:
        index = client.Index(settings.pinecone_index_name)

    logger.info(
        "pinecone_initialized",
        index_name=settings.pinecone_index_name,
        dimension=dimension,
    )
    return PineconeIndexAdapter(index)
