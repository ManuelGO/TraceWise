"""Database connection management."""

import asyncio
import logging

import redis.asyncio as redis

from app.db.database import (
    Base,
    create_db_engine,
    create_session_factory,
    get_db,
    health_check,
    init_db,
)
from app.db.session import (
    commit_session,
    flush_session,
    get_nested_transaction,
    get_transaction,
    get_transaction_for_dependency,
    rollback_session,
)

logger = logging.getLogger(__name__)


def __getattr__(name: str):
    """Lazy-load repositories to avoid circular imports with models."""
    if name == "ComplianceCaseRepository":
        from app.db.repositories.compliance_case import ComplianceCaseRepository
        return ComplianceCaseRepository
    elif name == "DocumentRepository":
        from app.db.repositories.document import DocumentRepository
        return DocumentRepository
    elif name == "ExtractedEvidenceRepository":
        from app.db.repositories.extracted_evidence import ExtractedEvidenceRepository
        return ExtractedEvidenceRepository
    elif name == "GeneratedReportRepository":
        from app.db.repositories.generated_report import GeneratedReportRepository
        return GeneratedReportRepository
    elif name == "ReviewDecisionRepository":
        from app.db.repositories.review_decision import ReviewDecisionRepository
        return ReviewDecisionRepository
    elif name == "RiskAssessmentRepository":
        from app.db.repositories.risk_assessment import RiskAssessmentRepository
        return RiskAssessmentRepository
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


async def connect_with_retry(
    database_url: str, redis_url: str, max_retries: int = 5
) -> tuple[redis.Redis | None, None]:
    """Establish Redis connection with exponential backoff retry logic.

    PostgreSQL connections are now managed exclusively via SQLAlchemy engine.
    This function handles Redis connectivity only.

    Returns:
        tuple: (redis_client, None) or (None, None) on failure
    """
    for attempt in range(max_retries):
        redis_client = None
        try:
            redis_client = redis.from_url(redis_url, decode_responses=True)
            await redis_client.ping()
            logger.info(f"Connected to Redis (attempt {attempt + 1})")
            return redis_client, None

        except (TimeoutError, redis.RedisError, OSError) as e:
            if redis_client:
                try:
                    await redis_client.aclose()
                except Exception as close_err:
                    logger.debug(f"Error closing Redis connection: {close_err}")

            delay = min(2**attempt, 16)
            if attempt < max_retries - 1:
                logger.warning(
                    f"Redis connection attempt {attempt + 1} failed: {e}. Retrying in {delay}s..."
                )
                await asyncio.sleep(delay)
            else:
                logger.error(f"Redis connection failed on attempt {attempt + 1}: {e}")

    logger.error(f"Failed to connect to Redis after {max_retries} attempts")
    return None, None


__all__ = [
    "connect_with_retry",
    "Base",
    "commit_session",
    "ComplianceCaseRepository",
    "create_db_engine",
    "create_session_factory",
    "DocumentRepository",
    "ExtractedEvidenceRepository",
    "flush_session",
    "GeneratedReportRepository",
    "get_db",
    "get_nested_transaction",
    "get_transaction",
    "get_transaction_for_dependency",
    "health_check",
    "init_db",
    "ReviewDecisionRepository",
    "RiskAssessmentRepository",
    "rollback_session",
]
