"""MongoDB connection lifecycle. The Motor client is reused for the app process."""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class MongoManager:
    def __init__(self) -> None:
        self.client: AsyncIOMotorClient | None = None
        self.db: AsyncIOMotorDatabase | None = None

    async def connect(self, settings: Settings) -> AsyncIOMotorDatabase:
        self.client = AsyncIOMotorClient(settings.mongodb_uri)
        self.db = self.client[settings.mongodb_db_name]
        await self.client.admin.command("ping")
        logger.info("mongo_connected", database=settings.mongodb_db_name)
        return self.db

    async def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
            self.db = None
            logger.info("mongo_disconnected")

    def get_db(self) -> Any:
        if self.db is None:
            raise RuntimeError("MongoDB has not been initialized")
        return self.db


mongo_manager = MongoManager()
