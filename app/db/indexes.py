"""Ensure required MongoDB indexes exist at startup."""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


async def ensure_indexes(db: Any) -> None:
    await db["users"].create_index("email", unique=True)
    await db["businesses"].create_index("uuid", unique=True)
    await db["businesses"].create_index("owner_user_id")
    await db["businesses"].create_index("created_at")
    try:
        await db["agent_checkpoints"].create_index("thread_id", unique=True)
        await db["agent_checkpoints"].create_index("business_uuid")
        await db["agent_checkpoint_writes"].create_index("thread_id", unique=True)
    except Exception:
        logger.warning("conversation_indexes_not_unique_yet")
    logger.info("mongo_indexes_ensured")
