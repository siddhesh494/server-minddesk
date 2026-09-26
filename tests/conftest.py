from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.integrations.whatsapp.client import FakeWhatsAppClient
from tests.fakes import FakeBusinessChatModel, FakeDatabase, FakeEmbeddings, FakePineconeIndex


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        api_prefix="/api",
        mongodb_uri="mongodb://localhost:27017",
        mongodb_db_name="rag_agent_test",
        jwt_secret_key="test-secret-key-which-is-long-enough",
        jwt_algorithm="HS256",
        jwt_expire_minutes=60,
        embedding_model="gemini-embedding-2",
        embedding_dimension=64,
        groq_model="openai/gpt-oss-20b",
        chunk_size=1000,
        chunk_overlap=150,
        retrieval_top_k=5,
        min_score=0.0,
        cors_origins="http://localhost:5173",
        whatsapp_api_version="v21.0",
        whatsapp_verify_token="test-verify-token",
        whatsapp_access_token="test-whatsapp-token",
        whatsapp_app_secret="test-app-secret",
    )


@pytest.fixture
def pinecone_index() -> FakePineconeIndex:
    return FakePineconeIndex()


@pytest.fixture
def app_db() -> FakeDatabase:
    return FakeDatabase()


@pytest.fixture
def whatsapp_client() -> FakeWhatsAppClient:
    return FakeWhatsAppClient()


@pytest.fixture
def client(
    settings: Settings,
    app_db: FakeDatabase,
    pinecone_index: FakePineconeIndex,
    whatsapp_client: FakeWhatsAppClient,
) -> TestClient:
    application = create_app(
        settings,
        testing=True,
        db=app_db,
        embeddings=FakeEmbeddings(settings),
        pinecone_index=pinecone_index,
        llm=FakeBusinessChatModel(),
        whatsapp_client=whatsapp_client,
    )
    with TestClient(application) as test_client:
        yield test_client


def auth_header(client: TestClient, suffix: str = "one") -> dict[str, str]:
    client.post(
        "/api/register",
        json={"name": f"Admin {suffix}", "email": f"admin-{suffix}@example.com", "password": "password12"},
    )
    response = client.post(
        "/api/login",
        json={"email": f"admin-{suffix}@example.com", "password": "password12"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
