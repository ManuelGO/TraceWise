"""Document processing tasks for Celery async job queue."""

import asyncio
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from app.celery_app import celery_app
from app.config import get_settings
from app.db.database import create_db_engine
from app.db.repositories.job import JobRepository
from app.db.session import get_transaction

logger = logging.getLogger(__name__)

# Module-level engine and session factory caching (FIX #2: prevent connection pool leak)
_engine = None
_session_factory = None


def _get_engine_and_factory():
    """Get or initialize cached engine and session factory.

    Engine is cached at the module level to prevent connection pool leaks.
    This ensures all tasks in a worker process share the same pool.

    Returns:
        Tuple of (engine, sessionmaker)
    """
    global _engine, _session_factory
    if _session_factory is None:
        settings = get_settings()
        _engine = create_db_engine(
            settings.DATABASE_URL,
            echo=settings.DB_ECHO,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_pre_ping=settings.DB_POOL_PRE_PING,
        )
        _session_factory = sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _engine, _session_factory


async def _get_session() -> AsyncSession:
    """Get a new session from the shared factory.

    Returns:
        AsyncSession: New session from the shared factory
    """
    _, session_factory = _get_engine_and_factory()
    return session_factory()


async def _run_job(job_id: str, action_name: str) -> None:
    """Shared job execution scaffold with state transitions.

    Handles marking job as processing, executing placeholder action,
    and transitioning to completed/failed states.

    Args:
        job_id: UUID of job to process
        action_name: Name of action for logging (e.g., "Validating document")

    Raises:
        ValueError: If job not found
        Exception: If action fails
    """
    session = await _get_session()

    try:
        async with get_transaction(session) as tx_session:
            job_repo = JobRepository()
            job = await job_repo.read(tx_session, UUID(job_id))

            if not job:
                raise ValueError(f"Job {job_id} not found")

            job.mark_processing()
            await tx_session.flush()
            logger.info(f"Job {job_id} marked as processing")

            # ===== BUSINESS LOGIC HOOK =====
            logger.info(f"{action_name} for job {job_id}")
            # Task 24 will insert validation logic here
            # Task 25 will insert extraction logic here
            # =================================

            job.mark_completed()
            logger.info(f"Job {job_id} completed successfully")

    except Exception as e:
        # FIX #1: Open fresh session for error recovery
        # (original session is closed by get_transaction's finally block)
        fail_session = await _get_session()
        try:
            async with get_transaction(fail_session) as fs:
                job_repo = JobRepository()
                job = await job_repo.read(fs, UUID(job_id))
                if job:
                    job.mark_failed(str(e))
                    logger.info(f"Job {job_id} marked as failed: {e}")
        except Exception as recovery_error:
            logger.error(
                f"Failed to mark job {job_id} as failed: {recovery_error}",
                exc_info=True,
            )
        logger.error(f"{action_name} for job {job_id} failed: {e}", exc_info=True)
        raise


def _run_task(task_name: str, job_id: str, action_name: str) -> None:
    """Sync wrapper for async job execution.

    Args:
        task_name: Name of Celery task (for logging)
        job_id: UUID of job to process
        action_name: Name of action for logging

    Raises:
        Exception: If action fails
    """
    try:
        asyncio.run(_run_job(job_id, action_name))
    except Exception as e:
        logger.error(f"{task_name} failed for job {job_id}: {e}", exc_info=True)
        raise


# ===== Celery Tasks =====


@celery_app.task(
    bind=True,
    name="app.tasks.document_tasks.validate_document_task",
    autoretry_for=(Exception,),
    max_retries=3,
)
def validate_document_task(self, job_id: str):
    """Validate document content asynchronously.

    This is a placeholder task for Task 24 (File Validation Service).

    Args:
        job_id: UUID of the job to validate (as string for JSON serialization)

    Raises:
        Exception: If validation fails or job not found
    """
    _run_task("validate_document_task", job_id, "Validating document")


@celery_app.task(
    bind=True,
    name="app.tasks.document_tasks.extract_text_task",
    autoretry_for=(Exception,),
    max_retries=3,
)
def extract_text_task(self, job_id: str):
    """Extract text from document asynchronously.

    This is a placeholder task for Task 25 (Text Extraction Service).

    Args:
        job_id: UUID of the job to extract text from (as string for JSON serialization)

    Raises:
        Exception: If extraction fails or job not found
    """
    _run_task("extract_text_task", job_id, "Extracting text from document")
