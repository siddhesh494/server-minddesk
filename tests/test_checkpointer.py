from bson import ObjectId
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.rag.checkpointer import (
    ConversationCheckpointer,
    history_from_checkpoint,
    messages_to_history,
    parse_thread_identity,
)


class FakeSyncCollection:
    def __init__(self) -> None:
        self.docs: list[dict] = []

    def create_index(self, *args, **kwargs) -> str:
        return "ok"

    def _matches(self, doc: dict, query: dict) -> bool:
        for key, expected in query.items():
            actual = doc.get(key)
            if isinstance(expected, dict) and "$ne" in expected:
                if actual == expected["$ne"]:
                    return False
            elif actual != expected:
                return False
        return True

    def find_one(self, query: dict, projection: dict | None = None) -> dict | None:
        for doc in self.docs:
            if self._matches(doc, query):
                return dict(doc)
        return None

    def find(self, query: dict):
        matches = [dict(doc) for doc in self.docs if self._matches(doc, query)]
        return FakeCursor(matches)

    def update_one(self, query: dict, update: dict, upsert: bool = False) -> None:
        for doc in self.docs:
            if self._matches(doc, query):
                if "$set" in update:
                    doc.update(update["$set"])
                return
        if upsert:
            stored = {"_id": ObjectId()}
            stored.update(update.get("$setOnInsert", {}))
            stored.update(update.get("$set", {}))
            self.docs.append(stored)

    def delete_many(self, query: dict) -> None:
        self.docs = [doc for doc in self.docs if not self._matches(doc, query)]


class FakeCursor:
    def __init__(self, docs: list[dict]) -> None:
        self.docs = docs

    def sort(self, key: str, direction: int = -1):
        self.docs.sort(key=lambda doc: doc.get(key) or 0, reverse=direction < 0)
        return self

    def limit(self, count: int):
        self.docs = self.docs[:count]
        return self

    def __iter__(self):
        return iter(self.docs)


def test_parse_thread_identity_splits_phone_and_uuid() -> None:
    phone, uuid = parse_thread_identity("919876543210:550e8400-e29b-41d4-a716-446655440000")
    assert phone == "919876543210"
    assert uuid == "550e8400-e29b-41d4-a716-446655440000"


def test_messages_to_history_keeps_send_order() -> None:
    history = messages_to_history(
        [
            HumanMessage(content="My name is Rahul."),
            AIMessage(content="", tool_calls=[{"name": "retrieve_business_information", "args": {"query": "hours"}, "id": "1"}]),
            ToolMessage(content="Open 9 to 6", tool_call_id="1", name="retrieve_business_information"),
            AIMessage(content="We are open 9 to 6."),
        ]
    )
    assert [item["seq"] for item in history] == [1, 2, 3, 4]
    assert [item["role"] for item in history] == ["user", "assistant", "tool", "assistant"]
    assert history[0]["content"] == "My name is Rahul."
    assert history[-1]["content"] == "We are open 9 to 6."


def test_history_from_checkpoint_reads_messages_channel() -> None:
    checkpoint = {
        "v": 1,
        "id": "ckpt-1",
        "ts": "2026-09-21T00:00:00+00:00",
        "channel_values": {
            "messages": [
                HumanMessage(content="Hello"),
                AIMessage(content="Hi, how can I help?"),
            ]
        },
        "channel_versions": {},
        "versions_seen": {},
        "updated_channels": None,
    }
    history = history_from_checkpoint(checkpoint)
    assert len(history) == 2
    assert history[0] == {"seq": 1, "role": "user", "content": "Hello"}
    assert history[1]["role"] == "assistant"


def test_checkpointer_keeps_one_document_with_history_array() -> None:
    checkpoints = FakeSyncCollection()
    writes = FakeSyncCollection()
    saver = ConversationCheckpointer(
        checkpoint_collection=checkpoints,
        writes_collection=writes,
    )
    thread_id = "919876543210:aaa-111"
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}

    first = {
        "v": 1,
        "id": "ckpt-1",
        "ts": "2026-09-21T00:00:00+00:00",
        "channel_values": {"messages": [HumanMessage(content="My name is Rahul.")]},
        "channel_versions": {"messages": 1},
        "versions_seen": {},
        "updated_channels": ["messages"],
    }
    second = {
        **first,
        "id": "ckpt-2",
        "channel_values": {
            "messages": [
                HumanMessage(content="My name is Rahul."),
                AIMessage(content="Nice to meet you, Rahul."),
            ]
        },
        "channel_versions": {"messages": 2},
    }

    saver.put(config, first, {"source": "input", "step": -1, "parents": {}}, {})
    saver.put(
        {**config, "configurable": {**config["configurable"], "checkpoint_id": "ckpt-1"}},
        second,
        {"source": "loop", "step": 1, "parents": {}},
        {},
    )
    saver.put_writes(
        {"configurable": {"thread_id": thread_id, "checkpoint_ns": "", "checkpoint_id": "ckpt-2"}},
        [("messages", AIMessage(content="Nice to meet you, Rahul."))],
        task_id="task-1",
    )

    assert len(checkpoints.docs) == 1
    assert len(writes.docs) == 1
    stored = checkpoints.docs[0]
    assert stored["thread_id"] == thread_id
    assert stored["customer_phone"] == "919876543210"
    assert stored["business_uuid"] == "aaa-111"
    assert stored["checkpoint_id"] == "ckpt-2"
    assert [item["seq"] for item in stored["history"]] == [1, 2]
    assert stored["history"][0]["content"] == "My name is Rahul."
    assert stored["history"][1]["role"] == "assistant"
    assert writes.docs[0]["write_count"] == 1
    assert writes.docs[0]["writes"][0]["seq"] == 1

    loaded = saver.get_tuple({"configurable": {"thread_id": thread_id}})
    assert loaded is not None
    assert loaded.checkpoint["id"] == "ckpt-2"
