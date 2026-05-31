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

    # S3 (dish photos). Defaults target local MinIO; for AWS set DP_S3_ENDPOINT_URL=""
    # (or the real endpoint), real keys, and DP_S3_PUBLIC_URL_BASE (bucket/CDN URL).
    s3_bucket: str = "dishport-photos"
    s3_region: str = "us-east-1"
    s3_endpoint_url: str | None = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_public_url_base: str | None = None  # defaults to endpoint + bucket

    # Providers. Absent in tests (in-memory fakes); required to actually run the gate.
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    # Models.
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    flavor_model: str = "claude-sonnet-4-6"

    # Dedup gate.
    dedup_tau: float = 0.90

    log_level: str = "INFO"
