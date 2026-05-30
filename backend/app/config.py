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
