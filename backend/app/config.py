"""Settings.

Env var conventions (mixed, on purpose — matches the deploy/secrets contract):
  * Supabase identity + Postgres use their own PLAIN names: SUPABASE_JWT_SECRET,
    SUPABASE_DB_URL. These are shared with the DB/frontend workstreams and the Fly secrets.
  * Everything else keeps the historical DP_ prefix: DP_OPENAI_API_KEY,
    DP_AZURE_STORAGE_CONNECTION_STRING, DP_LOG_LEVEL, etc.
The two Supabase fields are wired with an explicit validation_alias so the DP_ prefix is
NOT applied to them; `populate_by_name=True` still lets tests construct Settings(...) by the
Python field name.
"""
from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # Supabase Postgres (service connection — bypasses RLS). Standard postgresql:// DSN for
    # asyncpg (plain, not a SQLAlchemy +driver URL). Read from the plain env SUPABASE_DB_URL.
    database_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SUPABASE_DB_URL", "database_url"),
    )

    # Supabase-issued JWT verification. Modern projects sign access tokens ASYMMETRICALLY
    # (ES256) with a private key Supabase never shares; the worker verifies with the public key
    # from the project JWKS endpoint. Preferred over a shared HS256 secret (nothing forgeable if
    # the worker leaks). jwks_url derives from SUPABASE_URL if not set explicitly.
    supabase_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SUPABASE_URL", "supabase_url"),
    )
    supabase_jwks_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SUPABASE_JWKS_URL", "supabase_jwks_url"),
    )
    # Optional HS256 fallback for legacy projects that still use a shared secret.
    supabase_jwt_secret: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SUPABASE_JWT_SECRET", "supabase_jwt_secret"),
    )
    jwt_audience: str = "authenticated"   # Supabase stamps aud="authenticated"
    jwt_verify_audience: bool = True      # DP_JWT_VERIFY_AUDIENCE=false to disable the aud check

    @property
    def jwks_url(self) -> str | None:
        """JWKS endpoint for asymmetric (ES256) verification; derived from SUPABASE_URL."""
        if self.supabase_jwks_url:
            return self.supabase_jwks_url
        if self.supabase_url:
            return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        return None

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
    # OpenAI powers BOTH embeddings and the flavor/normalization call. Env: DP_OPENAI_API_KEY.
    openai_api_key: str | None = None

    # Models.
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    flavor_model: str = "gpt-4o-mini"

    # Dedup gate. 0.80 calibrated on real text-embedding-3-small over the enriched embedding
    # text (name+description+ingredients+prep): links true paraphrases (0.80-0.99), separates
    # distinct dishes (<=0.73), see scripts/calibrate_dedup.py.
    dedup_tau: float = 0.80

    log_level: str = "INFO"
