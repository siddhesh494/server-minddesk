from fastapi.testclient import TestClient

from tests.conftest import auth_header


def _create_business(client: TestClient, headers: dict[str, str], name: str, text: str) -> str:
    response = client.post("/api/index", headers=headers, json={"name": name, "text": text})
    assert response.status_code == 200
    return response.json()["uuid"]


def test_chat_with_valid_uuid(client: TestClient) -> None:
    headers = auth_header(client)
    uuid = _create_business(client, headers, "Laptop Store", "We sell laptops and monitors.")
    response = client.post(
        "/api/chat",
        json={
            "uuid": uuid,
            "user_phone_number": "+919999999999",
            "user_query": "What do you sell?",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["uuid"] == uuid
    assert body["thread_id"] == f"919999999999:{uuid}"
    assert "laptop" in body["answer"].lower()
    assert "pinecone" not in body["answer"].lower()


def test_chat_with_invalid_uuid(client: TestClient) -> None:
    response = client.post(
        "/api/chat",
        json={
            "uuid": "550e8400-e29b-41d4-a716-446655440000",
            "user_phone_number": "+919999999999",
            "user_query": "What do you sell?",
        },
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "BUSINESS_NOT_FOUND"


def test_business_uuid_isolation(client: TestClient) -> None:
    headers = auth_header(client)
    uuid_a = _create_business(client, headers, "Business A", "Business A sells laptops.")
    uuid_b = _create_business(client, headers, "Business B", "Business B sells coffee.")

    answer_a = client.post(
        "/api/chat",
        json={"uuid": uuid_a, "user_phone_number": "+919111111111", "user_query": "What does this business sell?"},
    ).json()["answer"]
    answer_b = client.post(
        "/api/chat",
        json={"uuid": uuid_b, "user_phone_number": "+919111111111", "user_query": "What does this business sell?"},
    ).json()["answer"]

    assert "laptop" in answer_a.lower()
    assert "coffee" not in answer_a.lower()
    assert "coffee" in answer_b.lower()
    assert "laptop" not in answer_b.lower()


def test_agent_uses_retrieved_business_knowledge(client: TestClient) -> None:
    headers = auth_header(client)
    uuid = _create_business(client, headers, "Device Shop", "We sell laptops and monitors.")
    response = client.post(
        "/api/chat",
        json={"uuid": uuid, "user_phone_number": "+919000000001", "user_query": "What do you sell?"},
    )
    answer = response.json()["answer"]
    assert "laptops" in answer.lower()
    assert "monitors" in answer.lower()


def test_short_term_memory_is_isolated_by_phone_and_uuid(client: TestClient) -> None:
    headers = auth_header(client)
    uuid_a = _create_business(client, headers, "Store A", "Store A sells laptops.")
    uuid_b = _create_business(client, headers, "Store B", "Store B sells coffee.")
    phone = "+91 9876543210"

    first = client.post(
        "/api/chat",
        json={"uuid": uuid_a, "user_phone_number": phone, "user_query": "My name is Rahul."},
    )
    assert first.status_code == 200

    remembered = client.post(
        "/api/chat",
        json={"uuid": uuid_a, "user_phone_number": phone, "user_query": "What is my name?"},
    )
    assert "Rahul" in remembered.json()["answer"]

    other_business = client.post(
        "/api/chat",
        json={"uuid": uuid_b, "user_phone_number": phone, "user_query": "What is my name?"},
    )
    assert "Rahul" not in other_business.json()["answer"]


def test_public_business_lookup(client: TestClient) -> None:
    headers = auth_header(client)
    uuid = _create_business(client, headers, "Demo Shop", "Demo Shop sells laptops.")
    response = client.get(f"/api/public/businesses/{uuid}")
    assert response.status_code == 200
    assert response.json()["name"] == "Demo Shop"
    assert "plain_text" not in response.json()
