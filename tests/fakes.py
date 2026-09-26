"""In-memory stand-ins so tests never call Mongo, Pinecone, Google, or Groq."""

from __future__ import annotations

import math
import re
from typing import Any
from uuid import uuid4

from bson import ObjectId
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pymongo.errors import DuplicateKeyError

from app.core.config import Settings


class FakeInsertOneResult:
    def __init__(self, inserted_id: Any) -> None:
        self.inserted_id = inserted_id


class FakeCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = list(docs)

    def sort(self, key: str, direction: int = -1) -> FakeCursor:
        reverse = direction < 0
        self.docs.sort(key=lambda doc: doc.get(key) or 0, reverse=reverse)
        return self

    def __aiter__(self):
        self._iter = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class FakeCollection:
    def __init__(self) -> None:
        self.docs: list[dict[str, Any]] = []
        self._unique: set[str] = set()

    async def create_index(self, *args: Any, **kwargs: Any) -> str:
        if args:
            self._unique.add(str(args[0]))
        return "ok"

    def _matches(self, doc: dict[str, Any], query: dict[str, Any]) -> bool:
        for key, expected in query.items():
            actual = doc.get(key)
            if isinstance(expected, dict) and "$in" in expected:
                if actual not in expected["$in"] and str(actual) not in [str(item) for item in expected["$in"]]:
                    return False
            elif actual != expected and str(actual) != str(expected):
                return False
        return True

    async def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        for doc in self.docs:
            if self._matches(doc, query):
                return dict(doc)
        return None

    def find(self, query: dict[str, Any]) -> FakeCursor:
        return FakeCursor([dict(doc) for doc in self.docs if self._matches(doc, query)])

    async def insert_one(self, document: dict[str, Any]) -> FakeInsertOneResult:
        stored = dict(document)
        if "email" in stored and any(doc.get("email") == stored["email"] for doc in self.docs):
            raise DuplicateKeyError("email")
        if "uuid" in stored and any(doc.get("uuid") == stored["uuid"] for doc in self.docs):
            raise DuplicateKeyError("uuid")
        if "message_id" in stored and any(doc.get("message_id") == stored["message_id"] for doc in self.docs):
            raise DuplicateKeyError("message_id")
        stored.setdefault("_id", ObjectId())
        self.docs.append(stored)
        return FakeInsertOneResult(stored["_id"])

    async def update_one(self, query: dict[str, Any], update: dict[str, Any]) -> None:
        changes = update.get("$set", update)
        for doc in self.docs:
            if self._matches(doc, query):
                doc.update(changes)
                return


class FakeDatabase:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> FakeCollection:
        if name not in self.collections:
            self.collections[name] = FakeCollection()
        return self.collections[name]


class FakeEmbeddings:
    def __init__(self, settings: Settings) -> None:
        self.dimension = settings.embedding_dimension

    def _vector(self, text: str) -> list[float]:
        tokens = set(re.findall(r"[a-z0-9]+", (text or "").lower()))
        stemmed = {token[:-1] if token.endswith("s") and len(token) > 3 else token for token in tokens}
        values = [0.0] * self.dimension
        for token in stemmed:
            index = sum(ord(char) for char in token) % self.dimension
            values[index] += 1.0
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return [value / norm for value in values]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class FakePineconeIndex:
    def __init__(self) -> None:
        self.namespaces: dict[str, dict[str, dict[str, Any]]] = {}
        self.fail_upsert = False

    def upsert(self, vectors: list[dict[str, Any]], namespace: str) -> dict[str, int]:
        if self.fail_upsert:
            raise RuntimeError("pinecone unavailable")
        bucket = self.namespaces.setdefault(namespace, {})
        for vector in vectors:
            bucket[vector["id"]] = {"values": vector["values"], "metadata": vector.get("metadata") or {}}
        return {"upserted_count": len(vectors)}

    def query(
        self,
        vector: list[float],
        top_k: int,
        namespace: str,
        include_metadata: bool = True,
    ) -> dict[str, Any]:
        bucket = self.namespaces.get(namespace, {})
        scored: list[dict[str, Any]] = []
        for item in bucket.values():
            score = _cosine(vector, item["values"])
            scored.append({"score": score, "metadata": item["metadata"] if include_metadata else {}})
        scored.sort(key=lambda item: item["score"], reverse=True)
        return {"matches": scored[:top_k]}

    def delete(self, *, delete_all: bool = False, namespace: str) -> None:
        if delete_all:
            self.namespaces.pop(namespace, None)

    def delete_namespace(self, namespace: str) -> None:
        self.namespaces.pop(namespace, None)


class FakeBusinessChatModel(BaseChatModel):
    """Deterministic tool-calling model used to exercise the real agent graph."""

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        last_human = _last_content(messages, HumanMessage)
        last_tool = _last_content(messages, ToolMessage)
        history_text = " ".join(
            str(message.content)
            for message in messages
            if isinstance(message, (HumanMessage, AIMessage)) and message.content
        )

        if last_tool:
            answer = _answer_from_tool(last_human, last_tool, history_text)
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=answer))])

        if last_human and _is_name_question(last_human):
            name = _extract_name(history_text)
            answer = f"Your name is {name}." if name else "I do not know your name yet."
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=answer))])

        if last_human and _is_name_introduction(last_human):
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="Nice to meet you."))])

        query = last_human or "business information"
        tool_call = {
            "name": "retrieve_business_information",
            "args": {"query": query},
            "id": f"call_{uuid4().hex[:8]}",
            "type": "tool_call",
        }
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[tool_call]))]
        )

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> FakeBusinessChatModel:
        return self

    @property
    def _llm_type(self) -> str:
        return "fake-business-chat"


def _cosine(left: list[float], right: list[float]) -> float:
    size = min(len(left), len(right))
    dot = sum(left[index] * right[index] for index in range(size))
    left_norm = math.sqrt(sum(value * value for value in left)) or 1.0
    right_norm = math.sqrt(sum(value * value for value in right)) or 1.0
    return dot / (left_norm * right_norm)


def _last_content(messages: list[BaseMessage], kind: type[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, kind) and message.content:
            return str(message.content)
    return ""


def _is_name_question(text: str) -> bool:
    lowered = text.lower()
    return "what is my name" in lowered or "what's my name" in lowered


def _is_name_introduction(text: str) -> bool:
    return "my name is" in text.lower()


def _extract_name(text: str) -> str | None:
    match = re.search(r"my name is ([A-Za-z]+)", text, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _answer_from_tool(question: str, tool_text: str, history_text: str) -> str:
    if "coffee" in tool_text.lower() and "laptop" not in tool_text.lower():
        return "We sell coffee."
    if "laptop" in tool_text.lower() or "monitor" in tool_text.lower():
        return "We sell laptops and monitors."
    if "No matching business knowledge" in tool_text:
        return "That information is not available in the business knowledge base."
    return tool_text
