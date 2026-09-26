from __future__ import annotations

import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.core.utils import normalize_phone_number
from app.integrations.whatsapp.client import FakeWhatsAppClient
from app.integrations.whatsapp.parser import parse_webhook_payload
from app.integrations.whatsapp.schemas import UNSUPPORTED_MESSAGE_REPLY
from tests.conftest import auth_header


def _sign(body: bytes, secret: str = "test-app-secret") -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _webhook_payload(
    *,
    phone_number_id: str,
    message_id: str,
    customer: str = "919876543210",
    text: str | None = "What do you sell?",
    message_type: str = "text",
) -> dict:
    message: dict = {
        "from": customer,
        "id": message_id,
        "timestamp": "1700000000",
        "type": message_type,
    }
    if message_type == "text":
        message["text"] = {"body": text}
    elif message_type == "image":
        message["image"] = {"id": "media-1"}
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba-1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": phone_number_id, "display_phone_number": "15550001234"},
                            "messages": [message],
                        },
                    }
                ],
            }
        ],
    }


def _post_webhook(client: TestClient, payload: dict, secret: str = "test-app-secret"):
    body = json.dumps(payload).encode("utf-8")
    return client.post(
        "/api/webhooks/whatsapp",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": _sign(body, secret),
        },
    )


def _create_business(client: TestClient, headers: dict[str, str], name: str, text: str) -> str:
    response = client.post("/api/index", headers=headers, json={"name": name, "text": text})
    assert response.status_code == 200
    return response.json()["uuid"]


def _connect(
    client: TestClient,
    headers: dict[str, str],
    uuid: str,
    phone_number_id: str,
) -> None:
    response = client.post(
        "/api/whatsapp/connect",
        headers=headers,
        json={
            "business_uuid": uuid,
            "phone_number_id": phone_number_id,
            "business_account_id": "waba-1",
            "display_phone_number": "+919876543210",
        },
    )
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "access_token" not in response.json()


def test_webhook_verification_accepts_valid_token(client: TestClient) -> None:
    response = client.get(
        "/api/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "test-verify-token", "hub.challenge": "challenge-123"},
    )
    assert response.status_code == 200
    assert response.text == "challenge-123"


def test_webhook_verification_rejects_invalid_token(client: TestClient) -> None:
    response = client.get(
        "/api/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "challenge-123"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "WHATSAPP_WEBHOOK_FORBIDDEN"


def test_webhook_rejects_invalid_signature(client: TestClient) -> None:
    payload = _webhook_payload(phone_number_id="phone-a", message_id="wamid.1")
    body = json.dumps(payload).encode("utf-8")
    response = client.post(
        "/api/webhooks/whatsapp",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256=deadbeef"},
    )
    assert response.status_code == 403


def test_parser_extracts_text_and_ignores_invalid_payload() -> None:
    payload = _webhook_payload(phone_number_id="123", message_id="wamid.abc", text="Hello")
    messages = parse_webhook_payload(payload)
    assert len(messages) == 1
    assert messages[0].text == "Hello"
    assert messages[0].phone_number_id == "123"
    assert parse_webhook_payload({"object": "page", "entry": []}) == []
    assert parse_webhook_payload(None) == []


def test_parser_marks_image_as_unsupported() -> None:
    payload = _webhook_payload(phone_number_id="123", message_id="wamid.img", message_type="image")
    messages = parse_webhook_payload(payload)
    assert messages[0].is_unsupported is True
    assert messages[0].is_text is False


def test_phone_normalization_matches_thread_ids() -> None:
    assert normalize_phone_number("+91 98765 43210") == "919876543210"
    assert normalize_phone_number("919876543210") == "919876543210"


def test_whatsapp_connect_requires_jwt_and_ownership(client: TestClient) -> None:
    owner = auth_header(client, "owner")
    other = auth_header(client, "other")
    uuid = _create_business(client, owner, "Shop", "We sell laptops.")

    denied = client.post(
        "/api/whatsapp/connect",
        json={
            "business_uuid": uuid,
            "phone_number_id": "phone-a",
            "business_account_id": "waba-1",
            "display_phone_number": "+919876543210",
        },
    )
    assert denied.status_code == 401

    forbidden = client.post(
        "/api/whatsapp/connect",
        headers=other,
        json={
            "business_uuid": uuid,
            "phone_number_id": "phone-a",
            "business_account_id": "waba-1",
            "display_phone_number": "+919876543210",
        },
    )
    assert forbidden.status_code == 403

    missing = client.get("/api/whatsapp/550e8400-e29b-41d4-a716-446655440000", headers=owner)
    assert missing.status_code == 404


def test_whatsapp_status_masks_phone_and_hides_secrets(client: TestClient) -> None:
    headers = auth_header(client)
    uuid = _create_business(client, headers, "Shop", "We sell laptops.")
    client.post(
        "/api/whatsapp/connect",
        headers=headers,
        json={
            "business_uuid": uuid,
            "phone_number_id": "phone-a",
            "business_account_id": "waba-1",
            "display_phone_number": "+919876543210",
            "access_token": "super-secret-token",
        },
    )
    status = client.get(f"/api/whatsapp/{uuid}", headers=headers)
    body = status.json()
    assert body["connected"] is True
    assert body["phone_number_id"] == "phone-a"
    assert "8765" not in body["display_phone_number"]
    assert "super-secret-token" not in json.dumps(body)
    assert "access_token" not in body


def test_whatsapp_disconnect_does_not_remove_business(client: TestClient) -> None:
    headers = auth_header(client)
    uuid = _create_business(client, headers, "Shop", "We sell laptops.")
    _connect(client, headers, uuid, "phone-a")
    deleted = client.delete(f"/api/whatsapp/{uuid}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "inactive"

    status = client.get(f"/api/whatsapp/{uuid}", headers=headers)
    assert status.json()["connected"] is False

    business = client.get(f"/api/businesses/{uuid}", headers=headers)
    assert business.status_code == 200
    assert business.json()["status"] == "active"


def test_whatsapp_text_message_uses_chatservice_and_sends_reply(
    client: TestClient,
    whatsapp_client: FakeWhatsAppClient,
) -> None:
    headers = auth_header(client)
    uuid = _create_business(client, headers, "Laptop Store", "We sell laptops and monitors.")
    _connect(client, headers, uuid, "phone-a")

    response = _post_webhook(
        client,
        _webhook_payload(phone_number_id="phone-a", message_id="wamid.123", text="What do you sell?"),
    )
    assert response.status_code == 200
    assert len(whatsapp_client.sent) == 1
    assert "laptop" in whatsapp_client.sent[0]["message"].lower()
    assert whatsapp_client.sent[0]["recipient_phone_number"] == "919876543210"


def test_whatsapp_business_not_found_does_not_call_agent(
    client: TestClient,
    whatsapp_client: FakeWhatsAppClient,
) -> None:
    response = _post_webhook(
        client,
        _webhook_payload(phone_number_id="unknown-phone", message_id="wamid.missing"),
    )
    assert response.status_code == 200
    assert whatsapp_client.sent == []


def test_duplicate_whatsapp_message_is_processed_once(
    client: TestClient,
    whatsapp_client: FakeWhatsAppClient,
) -> None:
    headers = auth_header(client)
    uuid = _create_business(client, headers, "Laptop Store", "We sell laptops and monitors.")
    _connect(client, headers, uuid, "phone-a")
    payload = _webhook_payload(phone_number_id="phone-a", message_id="wamid.123", text="What do you sell?")

    first = _post_webhook(client, payload)
    second = _post_webhook(client, payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert len(whatsapp_client.sent) == 1


def test_unsupported_whatsapp_type_gets_friendly_reply(
    client: TestClient,
    whatsapp_client: FakeWhatsAppClient,
) -> None:
    headers = auth_header(client)
    uuid = _create_business(client, headers, "Laptop Store", "We sell laptops.")
    _connect(client, headers, uuid, "phone-a")
    response = _post_webhook(
        client,
        _webhook_payload(phone_number_id="phone-a", message_id="wamid.img", message_type="image"),
    )
    assert response.status_code == 200
    assert whatsapp_client.sent[0]["message"] == UNSUPPORTED_MESSAGE_REPLY


def test_whatsapp_tenant_isolation(
    client: TestClient,
    whatsapp_client: FakeWhatsAppClient,
) -> None:
    headers = auth_header(client)
    uuid_a = _create_business(client, headers, "Business A", "Business A sells laptops.")
    uuid_b = _create_business(client, headers, "Business B", "Business B sells coffee.")
    _connect(client, headers, uuid_a, "phone-id-a")
    _connect(client, headers, uuid_b, "phone-id-b")

    _post_webhook(
        client,
        _webhook_payload(phone_number_id="phone-id-a", message_id="wamid.a", text="What do you sell?"),
    )
    assert "laptop" in whatsapp_client.sent[-1]["message"].lower()
    assert "coffee" not in whatsapp_client.sent[-1]["message"].lower()

    _post_webhook(
        client,
        _webhook_payload(phone_number_id="phone-id-b", message_id="wamid.b", text="What do you sell?"),
    )
    assert "coffee" in whatsapp_client.sent[-1]["message"].lower()
    assert "laptop" not in whatsapp_client.sent[-1]["message"].lower()


def test_whatsapp_memory_matches_api_thread(
    client: TestClient,
    whatsapp_client: FakeWhatsAppClient,
) -> None:
    headers = auth_header(client)
    uuid_a = _create_business(client, headers, "Store A", "Store A sells laptops.")
    uuid_b = _create_business(client, headers, "Store B", "Store B sells coffee.")
    _connect(client, headers, uuid_a, "phone-id-a")
    _connect(client, headers, uuid_b, "phone-id-b")

    _post_webhook(
        client,
        _webhook_payload(
            phone_number_id="phone-id-a",
            message_id="wamid.name",
            customer="919876543210",
            text="My name is Rahul.",
        ),
    )
    remembered = client.post(
        "/api/chat",
        json={"uuid": uuid_a, "user_phone_number": "+91 9876543210", "user_query": "What is my name?"},
    )
    assert "Rahul" in remembered.json()["answer"]
    assert remembered.json()["thread_id"] == f"919876543210:{uuid_a}"

    other = client.post(
        "/api/chat",
        json={"uuid": uuid_b, "user_phone_number": "+91 9876543210", "user_query": "What is my name?"},
    )
    assert "Rahul" not in other.json()["answer"]
    assert other.json()["thread_id"] == f"919876543210:{uuid_b}"


def test_whatsapp_send_failure_does_not_fail_webhook(
    client: TestClient,
    whatsapp_client: FakeWhatsAppClient,
) -> None:
    headers = auth_header(client)
    uuid = _create_business(client, headers, "Laptop Store", "We sell laptops.")
    _connect(client, headers, uuid, "phone-a")
    whatsapp_client.fail = True
    response = _post_webhook(
        client,
        _webhook_payload(phone_number_id="phone-a", message_id="wamid.fail", text="What do you sell?"),
    )
    assert response.status_code == 200
    assert whatsapp_client.sent == []


def test_whatsapp_test_endpoint_sends_message(
    client: TestClient,
    whatsapp_client: FakeWhatsAppClient,
) -> None:
    headers = auth_header(client)
    uuid = _create_business(client, headers, "Laptop Store", "We sell laptops.")
    _connect(client, headers, uuid, "phone-a")
    response = client.post(f"/api/whatsapp/{uuid}/test", headers=headers)
    assert response.status_code == 200
    assert len(whatsapp_client.sent) == 1
    assert "connected" in whatsapp_client.sent[0]["message"].lower()
