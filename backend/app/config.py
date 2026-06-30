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

    # Vector Store Configuration
    VECTOR_STORE_BACKEND: Literal["pgvector"] = Field(
        default="pgvector", description="Vector store backend (pgvector)"
    )
    VECTOR_STORE_INDEX_TYPE: Literal["ivfflat", "hnsw"] = Field(
        default="ivfflat", description="Vector index type (ivfflat or hnsw)"
    )
    VECTOR_STORE_INDEX_LISTS: int = Field(
        default=100, description="IVFFlat index lists parameter", ge=1, le=1000
    )
    VECTOR_STORE_PROBE: int = Field(
        default=10, description="IVFFlat probe parameter for search", ge=1, le=100
    )
    VECTOR_SEARCH_DEFAULT_K: int = Field(
        default=5, description="Default number of neighbors to return in similarity search", ge=1, le=100
    )
    VECTOR_SEARCH_SIMILARITY_THRESHOLD: float = Field(
        default=0.0, description="Minimum similarity score threshold (0.0 to 1.0)", ge=0.0, le=1.0
    )
    VECTOR_STORE_BATCH_SIZE: int = Field(
        default=100, description="Batch size for vector insert operations", ge=1, le=1000
    )

    # Retrieval Configuration
    RETRIEVAL_DEFAULT_K: int = Field(
        default=5, description="Default number of documents to retrieve", ge=1, le=100
    )
    RETRIEVAL_SIMILARITY_THRESHOLD: float = Field(
        default=0.0, description="Minimum similarity threshold for retrieval (0.0 to 1.0)", ge=0.0, le=1.0
    )
    RETRIEVAL_BATCH_SIZE: int = Field(
        default=10, description="Batch size for concurrent retrieval operations", ge=1, le=100
    )
    RERANKING_ENABLED: bool = Field(
        default=False, description="Enable optional reranking layer for retrieved results"
    )
    RETRIEVAL_CONTEXT_MAX_CHUNKS: int = Field(
        default=10, description="Max chunks included in the assembled grounded context", ge=1, le=100
    )
    RETRIEVAL_CONTEXT_MAX_CHARS: int = Field(
        default=8000, description="Max characters in the assembled grounded context", ge=100, le=100000
    )

    # LLM Configuration
    LLM_PROVIDER: str = Field(
        default="openrouter", description="LLM provider name"
    )
    LLM_PRIMARY_MODEL: str = Field(
        default="openai/gpt-4o-mini", description="Primary LLM model name (OpenRouter format)"
    )
    LLM_FALLBACK_MODEL: str = Field(
        default="meta-llama/llama-2-70b-chat", description="Fallback LLM model name (OpenRouter format)"
    )
    LLM_API_KEY: SecretStr = Field(
        default=SecretStr(""), description="LLM API key (defaults to OPENROUTER_API_KEY if set)"
    )
    LLM_TEMPERATURE: float = Field(
        default=0.7, description="Sampling temperature for LLM (0.0 to 2.0)", ge=0.0, le=2.0
    )
    LLM_MAX_TOKENS: int = Field(
        default=2048, description="Maximum tokens in LLM response", ge=1, le=8000
    )
    LLM_CONTEXT_MAX_TOKENS: int = Field(
        default=3000, description="Maximum tokens to include in context", ge=100, le=8000
    )
    LLM_TIMEOUT_SECONDS: float = Field(
        default=30.0, description="Timeout for LLM API requests (seconds)", ge=1.0, le=120.0
    )

    # Citation Configuration
    CITATION_TERM_THRESHOLD: int = Field(
        default=2, description="Minimum matching terms required for citation", ge=1, le=10
    )
    CITATION_MAX_COUNT: int = Field(
        default=5, description="Maximum citations to include in response", ge=1, le=20
    )
    CITATION_DISPLAY_FORMAT: Literal["markdown", "plain", "html"] = Field(
        default="markdown", description="Citation format (markdown, plain, html)"
    )
    CITATION_INCLUDE_CHUNK_TEXT: bool = Field(
        default=False, description="Include source chunk text in citation response"
    )

    # Evidence Validation Agent Configuration (Task 49)
    EVIDENCE_GROUNDING_MIN_CONFIDENCE: float = Field(
        default=0.3,
        description="Minimum citation confidence for a claim to count as grounded (0.0-1.0)",
        ge=0.0,
        le=1.0,
    )
    EVIDENCE_GROUNDING_MEDIUM_THRESHOLD: float = Field(
        default=0.5,
        description=(
            "Grounding score below this puts hallucination risk in the medium band; "
            "below EVIDENCE_GROUNDING_MIN_CONFIDENCE it is high (0.0-1.0)"
        ),
        ge=0.0,
        le=1.0,
    )
    EVIDENCE_GROUNDING_HIGH_THRESHOLD: float = Field(
        default=0.7,
        description="Grounding score at or above this puts hallucination risk in the low band (0.0-1.0)",
        ge=0.0,
        le=1.0,
    )

    # Report Generation Agent Configuration (Task 50)
    REPORT_MAX_EVIDENCE_ITEMS: int = Field(
        default=10,
        description="Maximum supporting-evidence items rendered in the report",
        ge=1,
        le=100,
    )
    REPORT_MAX_RISK_ITEMS: int = Field(
        default=20,
        description="Maximum individual risks/violations listed in the report",
        ge=1,
        le=100,
    )
    REPORT_INCLUDE_UNGROUNDED_EVIDENCE: bool = Field(
        default=True,
        description=(
            "Render-and-flag ungrounded/invalid evidence (is_valid=False) instead of omitting it; "
            "the evidence-validation gate is advisory, not a drop signal (Task 49-E)"
        ),
    )
    REPORT_LLM_SUMMARY_ENABLED: bool = Field(
        default=True,
        description=(
            "Use the LLM to write the executive summary; when False the agent always uses the "
            "deterministic template summary (the LLM path self-falls-back to it on failure either way)"
        ),
    )
    REPORT_SUMMARY_MAX_TOKENS: int = Field(
        default=512,
        description="Maximum tokens in the generated report executive summary",
        ge=1,
        le=4000,
    )

    # Entity Extraction Configuration (Task 38)
    EXTRACTION_TEMPERATURE: float = Field(
        default=0.3, description="Sampling temperature for entity extraction (0.0 to 2.0)", ge=0.0, le=2.0
    )
    EXTRACTION_MAX_TOKENS: int = Field(
        default=2000, description="Maximum tokens in extraction response", ge=512, le=8000
    )
    EXTRACTION_CONTEXT_LENGTH: int = Field(
        default=3000, description="Maximum tokens for extraction context", ge=100, le=8000
    )

    # Extraction Validation Configuration (Task 39)
    VALIDATION_MAX_RETRIES: int = Field(
        default=3, description="Maximum number of retry attempts for failed extractions", ge=1, le=10
    )
    VALIDATION_TIMEOUT: int = Field(
        default=60, description="Timeout for validation + retry pipeline (seconds)", ge=10, le=300
    )
    RETRY_BACKOFF_BASE: float = Field(
        default=1.0, description="Base backoff delay for retries (seconds)", ge=0.1, le=2.0
    )
    RETRY_BACKOFF_MULTIPLIER: float = Field(
        default=2.0, description="Exponential backoff multiplier", ge=1.0, le=2.0
    )
    VALIDATION_STRICT_MODE: bool = Field(
        default=False, description="If True, only 'valid' status is acceptable (no needs_improvement)"
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
