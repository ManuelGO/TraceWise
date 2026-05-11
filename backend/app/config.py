import os
from functools import lru_cache


class Settings:
    """Application settings loaded from environment variables."""

    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379")
    API_TITLE: str = "TraceWise API"
    API_VERSION: str = "0.1.0"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    settings = Settings()
    if not settings.DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable must be set")
    return settings
