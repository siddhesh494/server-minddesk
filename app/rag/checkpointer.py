"""One Mongo document per customer+business conversation.

LangGraph's default saver inserts a new checkpoint row on every graph step.
This saver keeps a single `agent_checkpoints` document keyed by thread_id
and a readable `history` array in send order.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator, Sequence
from datetime import UTC, datetime
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
    get_checkpoint_metadata,
)
from langgraph.checkpoint.mongodb.utils import dumps_metadata, loads_metadata
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from pymongo import MongoClient
from pymongo.collection import Collection

from app.core.logging import get_logger

logger = get_logger(__name__)


def parse_thread_identity(thread_id: str) -> tuple[str, str]:
    """Split `normalized_phone:business_uuid` without treating UUID hyphens as separators."""
    if ":" not in thread_id:
        return "", thread_id
    phone, business_uuid = thread_id.split(":", 1)
    return phone, business_uuid


def _text_from_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts).strip()
    return str(content).strip()


def messages_to_history(messages: Any) -> list[dict[str, Any]]:
    """Turn LangGraph message objects into a sequential, readable history array."""
    history: list[dict[str, Any]] = []
    if not messages:
        return history

    for message in messages:
        if isinstance(message, dict):
            raw_type = str(message.get("type") or message.get("role") or "")
            content = _text_from_content(message.get("content"))
            tool_calls = message.get("tool_calls") or []
            name = message.get("name")
        else:
            raw_type = str(getattr(message, "type", "") or "")
            content = _text_from_content(getattr(message, "content", ""))
            tool_calls = getattr(message, "tool_calls", None) or []
            name = getattr(message, "name", None)

        role = {
            "human": "user",
            "ai": "assistant",
            "tool": "tool",
            "system": "system",
        }.get(raw_type, raw_type or "unknown")

        entry: dict[str, Any] = {
            "seq": len(history) + 1,
            "role": role,
            "content": content,
        }
        if name:
            entry["name"] = name
        if tool_calls:
            entry["tool_calls"] = [
                {
                    "name": call.get("name") if isinstance(call, dict) else getattr(call, "name", ""),
                    "args": call.get("args") if isinstance(call, dict) else getattr(call, "args", {}),
                }
                for call in tool_calls
            ]
        history.append(entry)
    return history


def history_from_checkpoint(checkpoint: Checkpoint) -> list[dict[str, Any]]:
    messages = (checkpoint.get("channel_values") or {}).get("messages") or []
    return messages_to_history(messages)


class ConversationCheckpointer(BaseCheckpointSaver):
    """Stores one checkpoint document and one writes document per thread_id."""

    def __init__(
        self,
        client: MongoClient | None = None,
        db_name: str = "",
        checkpoint_collection_name: str = "agent_checkpoints",
        writes_collection_name: str = "agent_checkpoint_writes",
        *,
        checkpoint_collection: Collection | None = None,
        writes_collection: Collection | None = None,
    ) -> None:
        super().__init__()
        self.client = client
        self.serde = JsonPlusSerializer()
        if checkpoint_collection is not None and writes_collection is not None:
            self.checkpoint_collection = checkpoint_collection
            self.writes_collection = writes_collection
            return
        if client is None:
            raise ValueError("Mongo client is required")
        self.db = client[db_name]
        self.checkpoint_collection = self.db[checkpoint_collection_name]
        self.writes_collection = self.db[writes_collection_name]
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        try:
            self.checkpoint_collection.create_index("thread_id", unique=True)
            self.checkpoint_collection.create_index("business_uuid")
            self.writes_collection.create_index("thread_id", unique=True)
        except Exception:
            logger.warning("conversation_indexes_not_unique_yet")

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        thread_id = config["configurable"]["thread_id"]
        doc = self.checkpoint_collection.find_one({"thread_id": thread_id})
        if not doc:
            return None

        requested_id = get_checkpoint_id(config)
        if requested_id and requested_id != doc.get("checkpoint_id"):
            return None

        return self._doc_to_tuple(doc)

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        query: dict[str, Any] = {}
        if config is not None and "thread_id" in config.get("configurable", {}):
            query["thread_id"] = config["configurable"]["thread_id"]
        if before is not None:
            checkpoint_id = before.get("configurable", {}).get("checkpoint_id")
            if checkpoint_id:
                query["checkpoint_id"] = {"$lt": checkpoint_id}

        cursor = self.checkpoint_collection.find(query).sort("updated_at", -1)
        if limit:
            cursor = cursor.limit(limit)
        count = 0
        for doc in cursor:
            yield self._doc_to_tuple(doc)
            count += 1
            if limit and count >= limit:
                break

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = checkpoint["id"]
        phone, business_uuid = parse_thread_identity(thread_id)
        type_, serialized_checkpoint = self.serde.dumps_typed(checkpoint)
        metadata = get_checkpoint_metadata(config, metadata)
        now = datetime.now(tz=UTC)
        history = history_from_checkpoint(checkpoint)

        document = {
            "thread_id": thread_id,
            "customer_phone": phone,
            "business_uuid": business_uuid,
            "checkpoint_ns": checkpoint_ns,
            "checkpoint_id": checkpoint_id,
            "parent_checkpoint_id": config["configurable"].get("checkpoint_id"),
            "type": type_,
            "checkpoint": serialized_checkpoint,
            "metadata": dumps_metadata(self.serde, metadata),
            "history": history,
            "message_count": len(history),
            "updated_at": now,
        }
        self.checkpoint_collection.update_one(
            {"thread_id": thread_id},
            {"$set": document, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        self.checkpoint_collection.delete_many(
            {"thread_id": thread_id, "checkpoint_id": {"$ne": checkpoint_id}}
        )
        self._retain_current_writes(thread_id, checkpoint_id)
        logger.info("conversation_checkpoint_upserted", message_count=len(history))
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"]["checkpoint_id"]
        phone, business_uuid = parse_thread_identity(thread_id)
        now = datetime.now(tz=UTC)

        existing = self.writes_collection.find_one({"thread_id": thread_id}) or {}
        current = [
            item
            for item in existing.get("writes", [])
            if item.get("checkpoint_id") == checkpoint_id
        ]
        incoming_keys = {
            (task_id, WRITES_IDX_MAP.get(channel, idx))
            for idx, (channel, _value) in enumerate(writes)
        }
        current = [
            item
            for item in current
            if (item.get("task_id"), item.get("idx")) not in incoming_keys
        ]

        for idx, (channel, value) in enumerate(writes):
            type_, serialized_value = self.serde.dumps_typed(value)
            current.append(
                {
                    "seq": 0,
                    "checkpoint_id": checkpoint_id,
                    "checkpoint_ns": checkpoint_ns,
                    "task_id": task_id,
                    "task_path": task_path,
                    "idx": WRITES_IDX_MAP.get(channel, idx),
                    "channel": channel,
                    "type": type_,
                    "value": serialized_value,
                    "summary": _summarize_write(channel, value),
                    "created_at": now,
                }
            )

        current.sort(key=lambda item: (item.get("created_at") or now, item.get("idx") or 0))
        for seq, item in enumerate(current, start=1):
            item["seq"] = seq

        self.writes_collection.update_one(
            {"thread_id": thread_id},
            {
                "$set": {
                    "thread_id": thread_id,
                    "customer_phone": phone,
                    "business_uuid": business_uuid,
                    "checkpoint_id": checkpoint_id,
                    "writes": current,
                    "write_count": len(current),
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        writes_id = self._writes_id(thread_id)
        if writes_id is not None:
            self.writes_collection.delete_many({"thread_id": thread_id, "_id": {"$ne": writes_id}})

    def delete_thread(self, thread_id: str) -> None:
        self.checkpoint_collection.delete_many({"thread_id": thread_id})
        self.writes_collection.delete_many({"thread_id": thread_id})

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return await asyncio.to_thread(self.get_tuple, config)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        items = await asyncio.to_thread(
            lambda: list(self.list(config, filter=filter, before=before, limit=limit))
        )
        for item in items:
            yield item

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return await asyncio.to_thread(self.put, config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        await asyncio.to_thread(self.put_writes, config, writes, task_id, task_path)

    async def adelete_thread(self, thread_id: str) -> None:
        await asyncio.to_thread(self.delete_thread, thread_id)

    def _writes_id(self, thread_id: str) -> Any:
        doc = self.writes_collection.find_one({"thread_id": thread_id}, {"_id": 1})
        return None if doc is None else doc["_id"]

    def _retain_current_writes(self, thread_id: str, checkpoint_id: str) -> None:
        existing = self.writes_collection.find_one({"thread_id": thread_id})
        if not existing:
            return
        retained = [
            item
            for item in existing.get("writes", [])
            if item.get("checkpoint_id") == checkpoint_id
        ]
        for seq, item in enumerate(retained, start=1):
            item["seq"] = seq
        self.writes_collection.update_one(
            {"thread_id": thread_id},
            {
                "$set": {
                    "checkpoint_id": checkpoint_id,
                    "writes": retained,
                    "write_count": len(retained),
                    "updated_at": datetime.now(tz=UTC),
                }
            },
        )

    def _pending_writes(self, thread_id: str, checkpoint_id: str) -> list[tuple[str, str, Any]]:
        doc = self.writes_collection.find_one({"thread_id": thread_id})
        if not doc:
            return []
        pending: list[tuple[str, str, Any]] = []
        for item in sorted(doc.get("writes", []), key=lambda row: row.get("seq") or 0):
            if item.get("checkpoint_id") != checkpoint_id:
                continue
            pending.append(
                (
                    item["task_id"],
                    item["channel"],
                    self.serde.loads_typed((item["type"], item["value"])),
                )
            )
        return pending

    def _doc_to_tuple(self, doc: dict[str, Any]) -> CheckpointTuple:
        config_values = {
            "thread_id": doc["thread_id"],
            "checkpoint_ns": doc.get("checkpoint_ns", ""),
            "checkpoint_id": doc["checkpoint_id"],
        }
        parent = None
        if doc.get("parent_checkpoint_id"):
            parent = {
                "configurable": {
                    "thread_id": doc["thread_id"],
                    "checkpoint_ns": doc.get("checkpoint_ns", ""),
                    "checkpoint_id": doc["parent_checkpoint_id"],
                }
            }
        return CheckpointTuple(
            {"configurable": config_values},
            self.serde.loads_typed((doc["type"], doc["checkpoint"])),
            loads_metadata(self.serde, doc.get("metadata") or {}),
            parent,
            self._pending_writes(doc["thread_id"], doc["checkpoint_id"]),
        )


def _summarize_write(channel: str, value: Any) -> str:
    if channel != "messages":
        return channel
    history = messages_to_history(value if isinstance(value, list) else [value])
    if not history:
        return channel
    last = history[-1]
    content = last.get("content") or ""
    if len(content) > 180:
        content = content[:177] + "..."
    return f"{last.get('role')}: {content}".strip()
