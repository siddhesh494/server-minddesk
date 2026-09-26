from fastapi.testclient import TestClient

from tests.conftest import auth_header
from tests.fakes import FakePineconeIndex


def test_create_and_list_business(client: TestClient) -> None:
    headers = auth_header(client)
    created = client.post(
        "/api/index",
        headers=headers,
        json={"name": "ABC Electronics", "text": "ABC Electronics sells laptops and monitors."},
    )
    assert created.status_code == 200
    body = created.json()
    assert body["success"] is True
    assert body["version"] == 1
    assert body["chunk_count"] >= 1
    assert body["status"] == "active"
    uuid = body["uuid"]

    listed = client.get("/api/businesses", headers=headers)
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["uuid"] == uuid
    assert items[0]["name"] == "ABC Electronics"

    detail = client.get(f"/api/businesses/{uuid}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["plain_text"].startswith("ABC Electronics")
    assert "warm, short, and natural" in detail.json()["system_prompt"]


def test_custom_system_prompt_is_stored_per_business(client: TestClient) -> None:
    headers = auth_header(client)
    prompt = "You are a friendly coffee shop assistant. Always mention the daily roast."
    created = client.post(
        "/api/index",
        headers=headers,
        json={
            "name": "Brew House",
            "text": "Brew House sells coffee and pastries.",
            "system_prompt": prompt,
        },
    )
    uuid = created.json()["uuid"]
    detail = client.get(f"/api/businesses/{uuid}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["system_prompt"] == prompt

    updated_prompt = "You are a concise coffee shop assistant. Never mention other cafes."
    update = client.post(
        "/api/index/update",
        headers=headers,
        json={
            "uuid": uuid,
            "text": "Brew House sells coffee, tea, and pastries.",
            "system_prompt": updated_prompt,
        },
    )
    assert update.status_code == 200
    refreshed = client.get(f"/api/businesses/{uuid}", headers=headers)
    assert refreshed.json()["system_prompt"] == updated_prompt


def test_update_creates_new_version(
    client: TestClient,
    pinecone_index: FakePineconeIndex,
) -> None:
    headers = auth_header(client)
    created = client.post(
        "/api/index",
        headers=headers,
        json={"name": "ABC", "text": "We sell laptops."},
    )
    uuid = created.json()["uuid"]
    first_namespace = created.json()["namespace"]
    assert first_namespace in pinecone_index.namespaces

    updated = client.post(
        "/api/index/update",
        headers=headers,
        json={"uuid": uuid, "text": "We sell laptops and monitors.", "name": "ABC"},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["success"] is True
    assert body["version"] == 2
    assert first_namespace not in pinecone_index.namespaces
    assert any(namespace.endswith("--v2") for namespace in pinecone_index.namespaces)


def test_failed_update_preserves_previous_version(
    client: TestClient,
    pinecone_index: FakePineconeIndex,
) -> None:
    headers = auth_header(client)
    created = client.post(
        "/api/index",
        headers=headers,
        json={"name": "ABC", "text": "We sell laptops."},
    )
    uuid = created.json()["uuid"]
    original_namespace = created.json()["namespace"]
    pinecone_index.fail_upsert = True

    failed = client.post(
        "/api/index/update",
        headers=headers,
        json={"uuid": uuid, "text": "Updated text that should not replace the old index."},
    )
    assert failed.status_code == 502
    assert failed.json()["error"]["code"] in {"PINECONE_ERROR", "BUSINESS_INDEXING_FAILED"}
    assert original_namespace in pinecone_index.namespaces

    detail = client.get(f"/api/businesses/{uuid}", headers=headers)
    assert detail.json()["status"] == "active"
    assert detail.json()["active_namespace"] == original_namespace


def test_ownership_restriction(client: TestClient) -> None:
    owner = auth_header(client, "owner")
    created = client.post(
        "/api/index",
        headers=owner,
        json={"name": "Owner Shop", "text": "Owner Shop sells laptops."},
    )
    uuid = created.json()["uuid"]

    other = auth_header(client, "other")
    denied = client.get(f"/api/businesses/{uuid}", headers=other)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "BUSINESS_ACCESS_DENIED"

    update = client.post(
        "/api/index/update",
        headers=other,
        json={"uuid": uuid, "text": "Trying to overwrite another tenant."},
    )
    assert update.status_code == 403

    listed = client.get("/api/businesses", headers=other)
    assert listed.json()["items"] == []


def test_index_requires_auth(client: TestClient) -> None:
    response = client.post("/api/index", json={"name": "X", "text": "Y sells things."})
    assert response.status_code == 401
