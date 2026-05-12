from functools import lru_cache
from typing import Literal

from pydantic import ConfigDict, Field, SecretStr, field_validator
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

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v:
            raise ValueError("DATABASE_URL environment variable must be set")
        if not (v.startswith("postgresql://") or v.startswith("postgres://")):
            raise ValueError("DATABASE_URL must start with 'postgresql://' or 'postgres://'")
        return v

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


# NOTE: Settings are cached for the process lifetime.
# Rotating secrets (DATABASE_URL, REDIS_PASSWORD, etc.) requires a process restart.
# For hot-reload scenarios, replace @lru_cache() with a module-level singleton and expose
# a clear_settings_cache() function gated by environment.
@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
