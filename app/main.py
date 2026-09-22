"""FastAPI application factory, lifespan, and HTTP middleware."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from structlog.contextvars import bind_contextvars, clear_contextvars

from app.api.auth import router as auth_router
from app.api.businesses import router as businesses_router
from app.api.chat import router as chat_router
from app.api.index import router as index_router
from app.api.verify import router as verify_router
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.core.logging import configure_logging, get_logger
from app.db.indexes import ensure_indexes
from app.db.mongodb import mongo_manager
from app.rag.agent import build_agent, create_chat_model
from app.rag.embeddings import create_embedding_provider
from app.rag.memory import MemoryManager
from app.rag.pinecone_client import initialize_pinecone
from app.rag.retriever import BusinessRetriever
from app.repositories.business_repository import BusinessRepository

logger = get_logger(__name__)
memory_manager = MemoryManager()


def create_app(
    settings: Settings | None = None,
    *,
    testing: bool = False,
    db: Any = None,
    embeddings: Any = None,
    pinecone_index: Any = None,
    llm: Any = None,
    checkpointer: Any = None,
) -> FastAPI:
    settings = settings or get_settings()
    if testing:
        settings.app_env = "test"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging(settings.app_env)
        app.state.settings = settings

        if testing:
            if db is None or embeddings is None or pinecone_index is None or llm is None:
                raise RuntimeError("Test application requires db, embeddings, pinecone_index, and llm")
            app.state.db = db
            app.state.embeddings = embeddings
            app.state.pinecone_index = pinecone_index
            app.state.llm = llm
            app.state.checkpointer = checkpointer or memory_manager.initialize(settings, testing=True)
            await ensure_indexes(app.state.db)
            _bind_agent(app)
            logger.info("application_started", env="test")
            yield
            return

        settings.require_runtime_secrets()
        app.state.db = await mongo_manager.connect(settings)
        await ensure_indexes(app.state.db)
        app.state.pinecone_index = pinecone_index or initialize_pinecone(settings)
        app.state.embeddings = embeddings or create_embedding_provider(settings)
        app.state.llm = llm or create_chat_model(settings)
        app.state.checkpointer = checkpointer or memory_manager.initialize(settings, testing=False)
        _bind_agent(app)
        logger.info("application_started", env=settings.app_env)
        yield
        memory_manager.close()
        await mongo_manager.close()
        logger.info("application_stopped")

    app = FastAPI(
        title="MindDesk",
        description=(
            "Admin APIs index business knowledge into a shared Pinecone index. "
            "Public `/api/chat` answers customer questions from the matching business UUID only."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        clear_contextvars()
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        bind_contextvars(request_id=request_id)
        if int(request.headers.get("content-length") or 0) > settings.max_request_body_bytes:
            return JSONResponse(
                status_code=413,
                content={
                    "success": False,
                    "error": {"code": "INVALID_REQUEST", "message": "Request body is too large"},
                },
            )
        logger.info("request_started", method=request.method, path=request.url.path)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        message = "; ".join(
            f"{'.'.join(str(part) for part in error.get('loc', []))} {error.get('msg')}"
            for error in exc.errors()
        )
        return JSONResponse(
            status_code=422,
            content={"success": False, "error": {"code": "INVALID_REQUEST", "message": message}},
        )

    @app.exception_handler(ValidationError)
    async def pydantic_handler(_request: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"success": False, "error": {"code": "INVALID_REQUEST", "message": str(exc)}},
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(_request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled_exception", error_type=type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred"},
            },
        )

    prefix = settings.api_prefix.rstrip("/")
    app.include_router(auth_router, prefix=prefix)
    app.include_router(verify_router, prefix=prefix)
    app.include_router(verify_router)  # GET /verifyJWTToken as specified
    app.include_router(index_router, prefix=prefix)
    app.include_router(chat_router, prefix=prefix)
    app.include_router(businesses_router, prefix=prefix)

    @app.get("/health", tags=["System"], summary="Liveness probe")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _bind_agent(app: FastAPI) -> None:
    retriever = BusinessRetriever(
        businesses=BusinessRepository(app.state.db),
        embeddings=app.state.embeddings,
        index=app.state.pinecone_index,
        settings=app.state.settings,
    )
    app.state.retriever = retriever
    app.state.agent = build_agent(
        model=app.state.llm,
        retriever=retriever,
        checkpointer=app.state.checkpointer,
    )


app = create_app()
