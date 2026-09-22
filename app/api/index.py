from fastapi import APIRouter, Depends, Request

from app.dependencies.auth import get_current_user
from app.models.user import UserDocument
from app.rag.embeddings import EmbeddingProvider
from app.rag.pinecone_client import VectorIndex
from app.repositories.business_repository import BusinessRepository
from app.schemas.business import (
    IndexCreateRequest,
    IndexCreateResponse,
    IndexUpdateRequest,
    IndexUpdateResponse,
)
from app.services.indexing_service import IndexingService

router = APIRouter(tags=["Indexing"])


def _service(request: Request) -> IndexingService:
    return IndexingService(
        businesses=BusinessRepository(request.app.state.db),
        embeddings=request.app.state.embeddings,
        index=request.app.state.pinecone_index,
        settings=request.app.state.settings,
    )


@router.post(
    "/index",
    response_model=IndexCreateResponse,
    summary="Create and index a business knowledge base",
)
async def create_index(
    payload: IndexCreateRequest,
    request: Request,
    user: UserDocument = Depends(get_current_user),
) -> IndexCreateResponse:
    """Chunk text, embed it, store vectors in a new Pinecone namespace, and return a UUID."""
    embeddings: EmbeddingProvider = request.app.state.embeddings
    index: VectorIndex = request.app.state.pinecone_index
    _ = embeddings, index
    business = await _service(request).create_index(
        owner_user_id=str(user.id),
        name=payload.name,
        text=payload.text,
        editor_content=payload.editor_content,
        system_prompt=payload.system_prompt,
    )
    return IndexCreateResponse(
        uuid=business.uuid,
        version=business.active_version,
        chunk_count=business.chunk_count,
        namespace=business.active_namespace,
        status=business.status,
        message="Business indexed successfully.",
    )


@router.post(
    "/index/update",
    response_model=IndexUpdateResponse,
    summary="Re-index an existing business without changing its UUID",
)
async def update_index(
    payload: IndexUpdateRequest,
    request: Request,
    user: UserDocument = Depends(get_current_user),
) -> IndexUpdateResponse:
    """Write a new namespace first, then atomically switch MongoDB to it."""
    business = await _service(request).update_index(
        owner_user_id=str(user.id),
        uuid=payload.uuid,
        text=payload.text,
        name=payload.name,
        editor_content=payload.editor_content,
        system_prompt=payload.system_prompt,
    )
    return IndexUpdateResponse(
        uuid=business.uuid,
        version=business.active_version,
        chunk_count=business.chunk_count,
        message="Business knowledge updated successfully",
    )
