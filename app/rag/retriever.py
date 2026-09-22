"""Tenant-scoped retrieval. Namespace always comes from Mongo, never the client."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.core.exceptions import BusinessNotActiveError, BusinessNotFoundError, ChatError
from app.core.logging import get_logger
from app.rag.embeddings import EmbeddingProvider
from app.rag.pinecone_client import VectorIndex
from app.repositories.business_repository import BusinessRepository

logger = get_logger(__name__)


@dataclass
class RetrievedChunk:
    text: str
    score: float
    chunk_index: int


class BusinessRetriever:
    def __init__(
        self,
        *,
        businesses: BusinessRepository,
        embeddings: EmbeddingProvider,
        index: VectorIndex,
        settings: Settings,
    ) -> None:
        self.businesses = businesses
        self.embeddings = embeddings
        self.index = index
        self.settings = settings

    async def resolve_namespace(self, business_uuid: str) -> str:
        business = await self.businesses.get_by_uuid(business_uuid)
        if business is None:
            raise BusinessNotFoundError()
        if business.status != "active" or not business.active_namespace:
            raise BusinessNotActiveError()
        return business.active_namespace

    def search(self, business_uuid: str, namespace: str, query: str) -> list[RetrievedChunk]:
        """Search only the provided namespace. Callers must resolve it from Mongo."""
        logger.info("retrieval_started", business_uuid=business_uuid)
        try:
            vector = self.embeddings.embed_query(query)
            raw = self.index.query(
                vector=vector,
                top_k=self.settings.retrieval_top_k,
                namespace=namespace,
                include_metadata=True,
            )
        except Exception as exc:
            logger.error("retrieval_failed", business_uuid=business_uuid)
            raise ChatError("Unable to retrieve business knowledge") from exc

        matches = _extract_matches(raw)
        chunks: list[RetrievedChunk] = []
        for match in matches:
            score = float(match.get("score") or 0.0)
            if score < self.settings.min_score:
                continue
            metadata = match.get("metadata") or {}
            text = metadata.get("text") or ""
            if not text:
                continue
            chunks.append(
                RetrievedChunk(
                    text=text,
                    score=score,
                    chunk_index=int(metadata.get("chunk_index") or 0),
                )
            )
        logger.info(
            "retrieval_completed",
            business_uuid=business_uuid,
            result_count=len(chunks),
        )
        return chunks

    async def retrieve(self, business_uuid: str, query: str) -> list[RetrievedChunk]:
        namespace = await self.resolve_namespace(business_uuid)
        return self.search(business_uuid, namespace, query)


async def get_business_retriever(
    uuid: str,
    retriever: BusinessRetriever,
) -> tuple[str, BusinessRetriever]:
    """Resolve a tenant-safe retriever from the business UUID stored in MongoDB."""
    namespace = await retriever.resolve_namespace(uuid)
    return namespace, retriever


def _extract_matches(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, dict):
        return list(raw.get("matches") or [])
    matches = getattr(raw, "matches", None)
    if not matches:
        return []
    normalized: list[dict[str, Any]] = []
    for match in matches:
        if isinstance(match, dict):
            normalized.append(match)
            continue
        normalized.append(
            {
                "score": getattr(match, "score", 0.0),
                "metadata": getattr(match, "metadata", {}) or {},
            }
        )
    return normalized
