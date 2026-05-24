from functools import lru_cache
from typing import Literal

from pydantic import ConfigDict, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    # Environment
    ENVIRONMENT: Literal["development", "test", "production"] = Field(
        default="development", description="Deployment environment"
    )

    # API Configuration
    API_TITLE: str = Field(default="TraceWise API", description="API title")
    API_VERSION: str = Field(default="0.1.0", description="API version")
    API_HOST: str = Field(default="0.0.0.0", description="API bind address")
    API_PORT: int = Field(default=8000, description="API port", ge=1024, le=65535)

    # Database Configuration
    POSTGRES_USER: str = Field(default="postgres", description="PostgreSQL user")
    POSTGRES_PASSWORD: SecretStr = Field(
        default=SecretStr("postgres"), description="PostgreSQL password"
    )
    POSTGRES_DB: str = Field(default="tracewise", description="PostgreSQL database")
    DATABASE_URL: str = Field(
        default="",
        description="PostgreSQL connection string (postgresql://user:pass@host:port/db)",
    )

    # Redis Configuration
    REDIS_URL: str = Field(default="redis://redis:6379", description="Redis connection string")
    REDIS_PASSWORD: SecretStr = Field(
        default=SecretStr(""), description="Redis password (if needed)"
    )

    # Celery Configuration
    CELERY_BROKER_URL: str = Field(
        default="", description="Celery broker URL (auto-built from REDIS_URL + REDIS_PASSWORD)"
    )
    CELERY_BACKEND_URL: str = Field(
        default="", description="Celery backend URL (auto-built from REDIS_URL + REDIS_PASSWORD)"
    )

    # Logging Configuration
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Logging level"
    )

    # CORS Configuration
    CORS_ORIGINS: str = Field(
        default="http://localhost:4200",
        description="Comma-separated list of allowed CORS origins",
    )

    # Optional Performance Settings
    DB_POOL_SIZE: int = Field(default=10, description="Database connection pool size")
    DB_MAX_OVERFLOW: int = Field(default=20, description="Database pool overflow")
    DB_POOL_PRE_PING: bool = Field(
        default=True, description="Enable pool pre-ping (check connection health)"
    )
    DB_ECHO: bool = Field(default=False, description="Echo SQL statements")
    WORKERS: int = Field(default=4, description="Number of worker processes")
    TIMEOUT: int = Field(default=60, description="Request timeout in seconds")

    # File Storage Configuration
    STORAGE_PATH: str = Field(default="app/storage", description="Root directory for file storage")
    MAX_FILE_SIZE_MB: int = Field(default=50, description="Maximum file size in MB", ge=1)
    ALLOWED_MIME_TYPES: str = Field(
        default=(
            "application/pdf,"
            "image/jpeg,image/png,image/gif,image/webp,"
            "application/vnd.ms-excel,"
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
            "application/msword,"
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
            "text/plain,text/csv,application/json"
        ),
        description="Comma-separated list of allowed MIME types",
    )

    # Embedding Configuration
    OPENROUTER_API_KEY: SecretStr = Field(
        default=SecretStr(""), description="OpenRouter API key for embedding generation"
    )
    EMBEDDING_PRIMARY_MODEL: str = Field(
        default="openai/text-embedding-3-small", description="Primary embedding model (OpenRouter)"
    )
    EMBEDDING_FALLBACK_MODEL: str = Field(
        default="nomic-ai/nomic-embed-text-v1", description="Fallback embedding model (OpenRouter)"
    )
    EMBEDDING_BATCH_SIZE: int = Field(
        default=20, description="Batch size for embedding requests", ge=1, le=100
    )
    EMBEDDING_CACHE_TTL_SECONDS: int = Field(
        default=86400, description="Cache TTL for embeddings (default 24 hours)", ge=1
    )
    EMBEDDING_CACHE_ENABLED: bool = Field(
        default=True, description="Enable Redis caching for embeddings"
    )

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v:
            raise ValueError("DATABASE_URL environment variable must be set")
        if not (v.startswith("postgresql://") or v.startswith("postgres://")):
            raise ValueError("DATABASE_URL must start with 'postgresql://' or 'postgres://'")
        return v

    @model_validator(mode="after")
    def build_celery_urls(self) -> "Settings":
        """Build Celery URLs from REDIS_URL and REDIS_PASSWORD.

        If REDIS_PASSWORD is set and not already in REDIS_URL, embeds it.
        This ensures that when Redis requires authentication, Celery can authenticate.
        """
        pwd = self.REDIS_PASSWORD.get_secret_value()
        auth_base = self.REDIS_URL

        # Only add password if it's not already in the URL
        if pwd and f":{pwd}@" not in self.REDIS_URL:
            # Insert password: redis://redis:6379 → redis://:password@redis:6379
            auth_base = self.REDIS_URL.replace("redis://", f"redis://:{pwd}@", 1)

        self.CELERY_BROKER_URL = f"{auth_base}/0"
        self.CELERY_BACKEND_URL = f"{auth_base}/1"

        return self

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def validate_cors_origins(cls, v) -> str:
        raw = ",".join(v) if isinstance(v, list) else str(v)
        for origin in raw.split(","):
            origin = origin.strip()
            if origin == "*":
                raise ValueError(
                    "Wildcard '*' is not allowed for CORS_ORIGINS when credentials are enabled"
                )
            if not (
                origin.startswith("https://")
                or origin.startswith("http://localhost")
                or origin.startswith("http://127.0.0.1")
            ):
                raise ValueError(
                    f"CORS origin must be https:// (or localhost/127.0.0.1 for dev): {origin!r}"
                )
        return raw

    def get_cors_origins_list(self) -> list[str]:
        """Convert CORS_ORIGINS string to list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    def get_allowed_mime_types_list(self) -> list[str]:
        """Convert ALLOWED_MIME_TYPES string to list."""
        return [mime_type.strip() for mime_type in self.ALLOWED_MIME_TYPES.split(",")]

    def get_max_file_size_bytes(self) -> int:
        """Convert MAX_FILE_SIZE_MB to bytes."""
        return self.MAX_FILE_SIZE_MB * 1024 * 1024


# NOTE: Settings are cached for the process lifetime.
# Rotating secrets (DATABASE_URL, REDIS_PASSWORD, etc.) requires a process restart.
# For hot-reload scenarios, replace @lru_cache() with a module-level singleton and expose
# a clear_settings_cache() function gated by environment.
@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
