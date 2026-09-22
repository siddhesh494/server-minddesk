from fastapi.testclient import TestClient

from tests.conftest import auth_header


def test_register_and_login(client: TestClient) -> None:
    register = client.post(
        "/api/register",
        json={"name": "Admin", "email": "admin@example.com", "password": "password12"},
    )
    assert register.status_code == 200
    assert register.json()["email"] == "admin@example.com"
    assert "password" not in register.json()

    login = client.post(
        "/api/login",
        json={"email": "admin@example.com", "password": "password12"},
    )
    assert login.status_code == 200
    body = login.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_invalid_credentials(client: TestClient) -> None:
    client.post(
        "/api/register",
        json={"name": "Admin", "email": "admin@example.com", "password": "password12"},
    )
    response = client.post(
        "/api/login",
        json={"email": "admin@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 422
    assert response.json()["success"] is False
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_duplicate_registration(client: TestClient) -> None:
    payload = {"name": "Admin", "email": "admin@example.com", "password": "password12"}
    assert client.post("/api/register", json=payload).status_code == 200
    response = client.post("/api/register", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_verify_jwt_token(client: TestClient) -> None:
    headers = auth_header(client)
    ok = client.get("/verifyJWTToken", headers=headers)
    assert ok.status_code == 200
    assert ok.json() == {"authenticated": True}

    also_ok = client.get("/api/verifyJWTToken", headers=headers)
    assert also_ok.status_code == 200


def test_verify_jwt_token_rejects_missing_and_invalid(client: TestClient) -> None:
    missing = client.get("/verifyJWTToken")
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "AUTH_REQUIRED"

    invalid = client.get("/verifyJWTToken", headers={"Authorization": "Bearer not-a-token"})
    assert invalid.status_code == 401
    assert invalid.json()["error"]["code"] == "INVALID_TOKEN"


def test_protected_endpoint_without_token(client: TestClient) -> None:
    response = client.get("/api/businesses")
    assert response.status_code == 401
    assert response.json()["success"] is False
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"
