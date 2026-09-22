"""Create and safely version business knowledge in Pinecone."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from bson import ObjectId

from app.core.config import Settings
from app.core.exceptions import (
    BusinessAccessDeniedError,
    BusinessIndexingFailedError,
    BusinessNotFoundError,
    EmbeddingError,
    InvalidRequestError,
    PineconeError,
)
from app.core.logging import get_logger
from app.core.utils import build_namespace, build_vector_id, normalize_business_text, parse_uuid
from app.models.business import BusinessDocument
from app.rag.chunking import split_business_text
from app.rag.embeddings import EmbeddingProvider
from app.rag.pinecone_client import VectorIndex
from app.rag.prompts import resolve_system_prompt
from app.repositories.business_repository import BusinessRepository

logger = get_logger(__name__)


class IndexingService:
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

    async def create_index(
        self,
        *,
        owner_user_id: str,
        name: str,
        text: str,
        editor_content: str | dict[str, Any] | None = None,
        system_prompt: str | None = None,
    ) -> BusinessDocument:
        plain_text = normalize_business_text(text)
        if not plain_text:
            raise InvalidRequestError("Business text cannot be empty")

        business_uuid = str(uuid4())
        now = datetime.now(timezone.utc)
        owner_value: Any = ObjectId(owner_user_id) if ObjectId.is_valid(owner_user_id) else owner_user_id
        document = await self.businesses.create(
            {
                "uuid": business_uuid,
                "name": name.strip(),
                "editor_content": editor_content if editor_content is not None else plain_text,
                "plain_text": plain_text,
                "system_prompt": resolve_system_prompt(system_prompt),
                "active_version": 0,
                "active_namespace": "",
                "chunk_count": 0,
                "status": "indexing",
                "owner_user_id": owner_value,
                "created_at": now,
                "updated_at": now,
            }
        )
        logger.info("indexing_started", business_uuid=business_uuid)

        try:
            version = 1
            namespace = build_namespace(business_uuid, version)
            chunk_count = await self._index_version(business_uuid, version, namespace, plain_text)
            updated = await self.businesses.update_fields(
                business_uuid,
                {
                    "active_version": version,
                    "active_namespace": namespace,
                    "chunk_count": chunk_count,
                    "status": "active",
                },
            )
            logger.info("mongo_updated", business_uuid=business_uuid, namespace=namespace)
            logger.info("indexing_completed", business_uuid=business_uuid, chunk_count=chunk_count)
            assert updated is not None
            return updated
        except Exception as exc:
            await self.businesses.update_fields(business_uuid, {"status": "failed"})
            logger.error("indexing_failed", business_uuid=business_uuid)
            if isinstance(exc, (EmbeddingError, PineconeError, InvalidRequestError)):
                raise
            raise BusinessIndexingFailedError() from exc

    async def update_index(
        self,
        *,
        owner_user_id: str,
        uuid: str,
        text: str,
        name: str | None = None,
        editor_content: str | dict[str, Any] | None = None,
        system_prompt: str | None = None,
    ) -> BusinessDocument:
        try:
            business_uuid = parse_uuid(uuid)
        except ValueError as exc:
            raise BusinessNotFoundError() from exc

        business = await self.businesses.get_owned(business_uuid, owner_user_id)
        if business is None:
            existing = await self.businesses.get_by_uuid(business_uuid)
            if existing is None:
                raise BusinessNotFoundError()
            raise BusinessAccessDeniedError()

        plain_text = normalize_business_text(text)
        if not plain_text:
            raise InvalidRequestError("Business text cannot be empty")

        previous_namespace = business.active_namespace
        previous_version = business.active_version
        next_version = previous_version + 1 if previous_version > 0 else 1
        new_namespace = build_namespace(business_uuid, next_version)

        prompt_fields = (
            {"system_prompt": resolve_system_prompt(system_prompt)}
            if system_prompt is not None
            else {}
        )
        await self.businesses.update_fields(
            business_uuid,
            {
                "status": "indexing",
                "plain_text": plain_text,
                **({"name": name.strip()} if name else {}),
                **({"editor_content": editor_content} if editor_content is not None else {}),
                **prompt_fields,
            },
        )
        logger.info(
            "indexing_started",
            business_uuid=business_uuid,
            next_version=next_version,
        )

        try:
            chunk_count = await self._index_version(
                business_uuid,
                next_version,
                new_namespace,
                plain_text,
            )
            updated = await self.businesses.update_fields(
                business_uuid,
                {
                    "active_version": next_version,
                    "active_namespace": new_namespace,
                    "chunk_count": chunk_count,
                    "status": "active",
                    "plain_text": plain_text,
                    **({"name": name.strip()} if name else {}),
                    **({"editor_content": editor_content} if editor_content is not None else {}),
                    **prompt_fields,
                },
            )
            if updated is None:
                logger.error(
                    "pinecone_indexed_mongo_update_failed",
                    business_uuid=business_uuid,
                    new_namespace=new_namespace,
                )
                raise BusinessIndexingFailedError(
                    "Vectors were indexed but the business record could not be updated"
                )

            logger.info("mongo_updated", business_uuid=business_uuid, namespace=new_namespace)
            if previous_namespace and previous_namespace != new_namespace:
                await self._delete_namespace_safe(previous_namespace)
            logger.info("indexing_completed", business_uuid=business_uuid, chunk_count=chunk_count)
            return updated
        except Exception as exc:
            # Keep the previous working version if one exists.
            restore_status = "active" if previous_namespace else "failed"
            await self.businesses.update_fields(business_uuid, {"status": restore_status})
            logger.error("indexing_failed", business_uuid=business_uuid)
            if isinstance(exc, (EmbeddingError, PineconeError, InvalidRequestError, BusinessIndexingFailedError)):
                raise
            raise BusinessIndexingFailedError() from exc

    async def _index_version(
        self,
        business_uuid: str,
        version: int,
        namespace: str,
        text: str,
    ) -> int:
        chunks = split_business_text(text, self.settings)
        if not chunks:
            raise InvalidRequestError("No indexable text was produced")
        logger.info("text_chunked", business_uuid=business_uuid, chunk_count=len(chunks))

        try:
            vectors_values = await asyncio.to_thread(self.embeddings.embed_documents, chunks)
        except Exception as exc:
            logger.error("embedding_generation_failed", business_uuid=business_uuid)
            raise EmbeddingError() from exc
        logger.info("embeddings_generated", business_uuid=business_uuid, chunk_count=len(vectors_values))

        if len(vectors_values) != len(chunks):
            raise EmbeddingError("Embedding count did not match chunk count")
        for values in vectors_values:
            if len(values) != self.settings.embedding_dimension:
                raise EmbeddingError(
                    f"Embedding dimension {len(values)} does not match "
                    f"EMBEDDING_DIMENSION={self.settings.embedding_dimension}"
                )

        vectors = [
            {
                "id": build_vector_id(business_uuid, version, index),
                "values": values,
                "metadata": {
                    "business_uuid": business_uuid,
                    "version": version,
                    "chunk_index": index,
                    "text": chunk,
                    "source": "business_knowledge",
                },
            }
            for index, (chunk, values) in enumerate(zip(chunks, vectors_values))
        ]
        logger.info("pinecone_upsert_started", business_uuid=business_uuid, namespace=namespace)
        try:
            await asyncio.to_thread(self.index.upsert, vectors, namespace)
        except Exception as exc:
            logger.error("pinecone_upsert_failed", business_uuid=business_uuid)
            raise PineconeError() from exc
        logger.info("pinecone_upsert_completed", business_uuid=business_uuid, namespace=namespace)
        return len(chunks)

    async def _delete_namespace_safe(self, namespace: str) -> None:
        try:
            await asyncio.to_thread(
                lambda: self.index.delete(delete_all=True, namespace=namespace)
            )
        except Exception:
            logger.error("pinecone_namespace_delete_failed", namespace=namespace)
