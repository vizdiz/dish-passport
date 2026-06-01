"""Settings, loaded from DP_-prefixed env vars (and an optional .env)."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Infra (asyncpg DSN — plain postgresql://, not a SQLAlchemy +driver URL).
    database_url: str | None = None

    # Celery (batch scheduler). Broker + result backend default to local Redis.
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Azure Blob Storage (dish photos). Defaults target the local Azurite emulator with a
    # generated dev key (matches AZURITE_ACCOUNTS in docker-compose; a local stand-in, not a
    # secret). In prod set DP_AZURE_STORAGE_CONNECTION_STRING to the real account and
    # DP_AZURE_BLOB_PUBLIC_BASE to the public container / CDN base.
    azure_storage_connection_string: str = (
        "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;"
        "AccountKey=AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8gISIjJCUmJygpKissLS4v;"
        "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
    )
    azure_storage_container: str = "dishport-photos"
    azure_blob_public_base: str | None = None  # defaults to blob endpoint + container

    # Provider. Absent in tests (in-memory fakes); required to actually run the gate.
    # OpenAI powers BOTH embeddings and the flavor/normalization call.
    openai_api_key: str | None = None

    # Models.
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    flavor_model: str = "gpt-4o-mini"

    # Auth (JWT). Set a strong DP_JWT_SECRET in any real deployment (>= 32 bytes).
    jwt_secret: str = "dev-only-insecure-secret-change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 30  # 30 days (mobile-friendly)

    # Dedup gate. 0.80 calibrated on real text-embedding-3-small over the enriched embedding
    # text (name+description+ingredients+prep): links true paraphrases (0.80-0.99), separates
    # distinct dishes (<=0.73), see scripts/calibrate_dedup.py.
    dedup_tau: float = 0.80

    log_level: str = "INFO"
