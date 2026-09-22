"""LangGraph checkpointing. Conversation state is isolated by thread_id."""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from pymongo import MongoClient

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.utils import build_thread_id
from app.rag.checkpointer import ConversationCheckpointer

logger = get_logger(__name__)


class MemoryManager:
    def __init__(self) -> None:
        self.checkpointer: Any = None
        self._client: MongoClient | None = None

    def initialize(self, settings: Settings, *, testing: bool = False) -> Any:
        if testing:
            self.checkpointer = InMemorySaver()
            logger.info("checkpointer_initialized", backend="memory")
            return self.checkpointer

        self._client = MongoClient(settings.mongodb_uri)
        self.checkpointer = ConversationCheckpointer(
            self._client,
            db_name=settings.mongodb_db_name,
            checkpoint_collection_name="agent_checkpoints",
            writes_collection_name="agent_checkpoint_writes",
        )
        logger.info("checkpointer_initialized", backend="conversation_document")
        return self.checkpointer

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
            logger.info("checkpointer_closed")


def create_thread_id(phone: str, business_uuid: str) -> str:
    return build_thread_id(phone, business_uuid)
