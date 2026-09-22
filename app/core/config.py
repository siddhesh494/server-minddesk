"""Central application configuration.

Environment aliases are accepted so local setups can use either the
specification names or the operator-provided names (MONGO_URI, GEMINI_API_KEY, etc.).
"""

from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"
    api_prefix: str = "/api"

    mongodb_uri: str = Field(
        default="mongodb://localhost:27017",
        validation_alias=AliasChoices("MONGODB_URI", "MONGO_URI"),
    )
    mongodb_db_name: str = Field(
        default="rag_agent",
        validation_alias=AliasChoices("MONGODB_DB_NAME", "DATABASE_NAME"),
    )

    jwt_secret_key: str = Field(
        default="change-me",
        validation_alias=AliasChoices("JWT_SECRET_KEY", "JWT_SECRET"),
    )
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = Field(
        default=1440,
        validation_alias=AliasChoices("JWT_EXPIRE_MINUTES", "ACCESS_TOKEN_EXPIRE_MINUTES"),
    )

    pinecone_api_key: str = ""
    pinecone_index_name: str = "business-knowledge"
    pinecone_index_host: str = ""

    google_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GOOGLE_API_KEY", "GEMINI_API_KEY"),
    )
    embedding_model: str = "gemini-embedding-2"
    embedding_dimension: int = 3072

    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"

    chunk_size: int = 1000
    chunk_overlap: int = 150

    retrieval_top_k: int = Field(
        default=5,
        validation_alias=AliasChoices("RETRIEVAL_TOP_K", "TOP_K"),
    )
    min_score: float = 0.35

    cors_origins: str = "http://localhost:5173"
    max_request_body_bytes: int = 600_000

    langsmith_tracing: bool = False
    langsmith_api_key: str = ""

    @field_validator("chunk_overlap")
    @classmethod
    def overlap_must_be_smaller(cls, value: int, info) -> int:
        chunk_size = info.data.get("chunk_size", 1000)
        if value >= chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        return value

    @property
    def is_test(self) -> bool:
        return self.app_env.lower() == "test"

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def require_runtime_secrets(self) -> None:
        """Fail fast in non-test environments when required integrations are missing."""
        if self.is_test:
            return
        missing: list[str] = []
        if not self.mongodb_uri:
            missing.append("MONGODB_URI")
        if not self.jwt_secret_key or self.jwt_secret_key == "change-me":
            if self.is_production:
                missing.append("JWT_SECRET_KEY")
        if not self.pinecone_api_key:
            missing.append("PINECONE_API_KEY")
        if not self.pinecone_index_name:
            missing.append("PINECONE_INDEX_NAME")
        if not self.google_api_key:
            missing.append("GOOGLE_API_KEY")
        if not self.groq_api_key:
            missing.append("GROQ_API_KEY")
        if missing:
            raise RuntimeError(f"Missing required configuration: {', '.join(missing)}")


@lru_cache
def get_settings() -> Settings:
    return Settings()
