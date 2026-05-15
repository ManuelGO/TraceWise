"""Document processing tasks for Celery async job queue."""

import asyncio
import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from app.celery_app import celery_app
from app.config import get_settings
from app.db.database import create_db_engine
from app.db.repositories.document import DocumentRepository
from app.db.repositories.job import JobRepository
from app.db.session import get_transaction
from app.exceptions import (
    FileExtensionMismatchError,
    FileSizeTooLargeError,
    MimeTypeNotAllowedError,
)
from app.services.file_validator import (
    validate_extension,
    validate_file_size,
    validate_mime_type,
)

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


async def _mark_job_failed(job_id: str, reason: str) -> None:
    """Mark a job as failed in a fresh session (error recovery).

    Args:
        job_id: UUID of job to mark as failed
        reason: Error reason message
    """
    fail_session = await _get_session()
    try:
        async with get_transaction(fail_session) as fs:
            job_repo = JobRepository()
            job = await job_repo.read(fs, UUID(job_id))
            if job:
                job.mark_failed(reason)
                logger.info(f"Job {job_id} marked as failed: {reason}")
    except Exception as recovery_error:
        logger.error(
            f"Failed to mark job {job_id} as failed: {recovery_error}",
            exc_info=True,
        )


async def _validate_document(session: AsyncSession, job_id: UUID) -> None:
    """Execute document file validation logic.

    Validates file size, MIME type via magic bytes, and extension consistency.
    Updates Document.mime_type with detected value on success.

    Args:
        session: AsyncSession for database access
        job_id: UUID of job to validate

    Raises:
        FileSizeTooLargeError: If file exceeds 50MB limit
        MimeTypeNotAllowedError: If MIME type not in supported list
        FileExtensionMismatchError: If extension doesn't match detected MIME
        ValueError: If document or file not found
    """
    settings = get_settings()
    job_repo = JobRepository()
    doc_repo = DocumentRepository()

    job = await job_repo.read(session, job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")

    doc_id = job.job_metadata.get("document_id") if job.job_metadata else None
    if not doc_id:
        raise ValueError(f"Job {job_id} has no document_id in metadata; document_id must be passed in job_metadata")

    document = await doc_repo.read(session, UUID(doc_id))
    if not document:
        raise ValueError(f"Document {doc_id} not found")

    # FIX #2: Re-validate storage path boundary before reading file (path traversal prevention)
    storage_root = Path(settings.STORAGE_PATH).resolve()
    storage_path = (storage_root / document.storage_path).resolve()

    try:
        storage_path.relative_to(storage_root)
    except ValueError:
        raise ValueError(
            f"Document storage_path escapes storage root: {document.storage_path!r}"
        )

    if not storage_path.exists():
        raise FileNotFoundError(f"File not found at {document.storage_path!r}")

    file_bytes = storage_path.read_bytes()
    logger.info(
        f"Loaded file for validation: {document.storage_path} ({len(file_bytes)} bytes)"
    )

    validate_file_size(len(file_bytes))
    logger.info(f"File size validation passed for document {document.id}")

    detected_mime = validate_mime_type(file_bytes)
    logger.info(f"MIME type validation passed: detected {detected_mime}")

    validate_extension(document.filename, detected_mime)
    logger.info(f"Extension validation passed for {document.filename}")

    document.mime_type = detected_mime
    await session.flush()
    logger.info(f"Updated document.mime_type to {detected_mime}")


async def _run_job(
    job_id: str,
    action_name: str,
    business_logic_fn=None,
) -> None:
    """Shared job execution scaffold with state transitions.

    Handles marking job as processing, executing business logic,
    and transitioning to completed/failed states.

    Args:
        job_id: UUID of job to process
        action_name: Name of action for logging (e.g., "Validating document")
        business_logic_fn: Optional async function to execute (receives session, job_id UUID)

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

            if business_logic_fn:
                await business_logic_fn(tx_session, UUID(job_id))
                logger.info(f"{action_name} for job {job_id} completed")

            job.mark_completed()
            logger.info(f"Job {job_id} completed successfully")

    except (
        FileSizeTooLargeError,
        MimeTypeNotAllowedError,
        FileExtensionMismatchError,
        ValueError,
        FileNotFoundError,
    ) as ve:
        # FIX #1: Validation and permanent errors: fail immediately, do NOT retry
        logger.warning(f"Permanent error for job {job_id}: {ve}")
        await _mark_job_failed(job_id, str(ve))
        return

    except Exception as e:
        # System errors: allow Celery to retry
        logger.error(f"{action_name} for job {job_id} failed: {e}", exc_info=True)
        await _mark_job_failed(job_id, str(e))
        raise


def _run_task(
    task_name: str,
    job_id: str,
    action_name: str,
    business_logic_fn=None,
) -> None:
    """Sync wrapper for async job execution.

    Args:
        task_name: Name of Celery task (for logging)
        job_id: UUID of job to process
        action_name: Name of action for logging
        business_logic_fn: Optional async function to execute

    Raises:
        Exception: If action fails
    """
    try:
        asyncio.run(_run_job(job_id, action_name, business_logic_fn))
    except Exception as e:
        logger.error(f"{task_name} failed for job {job_id}: {e}", exc_info=True)
        raise


# ===== Celery Tasks =====


@celery_app.task(
    bind=True,
    name="app.tasks.document_tasks.validate_document_task",
    autoretry_for=(Exception,),
    dont_autoretry_for=(
        FileSizeTooLargeError,
        MimeTypeNotAllowedError,
        FileExtensionMismatchError,
        ValueError,
        FileNotFoundError,
    ),
    max_retries=3,
)
def validate_document_task(self, job_id: str) -> None:
    """Validate document content asynchronously.

    Validates file size (≤50MB), MIME type via magic bytes, and extension
    consistency. On success, updates Document.mime_type with detected value.
    On validation errors, marks job as failed immediately (no retry).

    Args:
        job_id: UUID of the job to validate (as string for JSON serialization)

    Raises:
        Exception: If system error occurs; validation errors don't retry
    """
    _run_task(
        "validate_document_task",
        job_id,
        "Validating document",
        _validate_document,
    )


@celery_app.task(
    bind=True,
    name="app.tasks.document_tasks.extract_text_task",
    autoretry_for=(Exception,),
    max_retries=3,
)
def extract_text_task(self, job_id: str) -> None:
    """Extract text from document asynchronously.

    This is a placeholder task for Task 25 (Text Extraction Service).

    Args:
        job_id: UUID of the job to extract text from (as string for JSON serialization)

    Raises:
        Exception: If extraction fails or job not found
    """
    _run_task(
        "extract_text_task",
        job_id,
        "Extracting text from document",
        None,
    )
