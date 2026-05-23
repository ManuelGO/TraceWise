"""Document processing tasks for Celery async job queue."""

import asyncio
import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from app.celery_app import celery_app
from app.config import get_settings
from app.db.database import create_db_engine
from app.db.repositories.document import DocumentRepository
from app.db.repositories.document_extraction import DocumentExtractionRepository
from app.db.repositories.job import JobRepository
from app.db.session import get_transaction
from app.exceptions import (
    FileExtensionMismatchError,
    FileSizeTooLargeError,
    MimeTypeNotAllowedError,
)
from app.models import DocumentExtraction
from app.monitoring.retry_metrics import (
    _sanitize_log,
    log_retry_attempt,
    log_retry_exhausted,
)
from app.services.dead_letter_handler import move_to_dlq
from app.services.file_validator import (
    validate_extension,
    validate_file_size,
    validate_mime_type,
)
from app.services.text_chunker import TextChunker
from app.services.text_extractor import (
    ExtractionError,
    extract_from_csv,
    extract_from_docx,
    extract_from_pdf,
    extract_from_txt,
    extract_from_xlsx,
)
from app.utils.idempotency import generate_idempotency_key

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


async def _move_to_dlq_async(
    session: AsyncSession,
    job_id: UUID,
    error_message: str,
    retry_count: int,
) -> None:
    """Async wrapper for move_to_dlq within a transaction.

    Args:
        session: AsyncSession for database access
        job_id: UUID of job to move to DLQ
        error_message: Error message from final failure
        retry_count: Number of retries attempted
    """
    try:
        async with get_transaction(session) as tx_session:
            await move_to_dlq(
                session=tx_session,
                job_id=job_id,
                error_message=error_message,
                retry_count=retry_count,
            )
    except Exception as e:
        logger.error(
            f"Error in DLQ handler for job {job_id}: {e}",
            exc_info=True,
        )
        raise


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
        raise ValueError(
            f"Job {job_id} has no document_id in metadata; "
            "document_id must be passed in job_metadata"
        )

    document = await doc_repo.read(session, UUID(doc_id))
    if not document:
        raise ValueError(f"Document {doc_id} not found")

    # FIX #2: Re-validate storage path boundary before reading file (path traversal prevention)
    storage_root = Path(settings.STORAGE_PATH).resolve()
    storage_path = (storage_root / document.storage_path).resolve()

    try:
        storage_path.relative_to(storage_root)
    except ValueError:
        raise ValueError(f"Document storage_path escapes storage root: {document.storage_path!r}")

    if not storage_path.exists():
        raise FileNotFoundError(f"File not found at {document.storage_path!r}")

    file_bytes = storage_path.read_bytes()
    logger.info(f"Loaded file for validation: {_sanitize_log(str(document.storage_path))} ({len(file_bytes)} bytes)")

    validate_file_size(len(file_bytes))
    logger.info(f"File size validation passed for document {document.id}")

    detected_mime = validate_mime_type(file_bytes)
    logger.info(f"MIME type validation passed: detected {detected_mime}")

    validate_extension(str(document.filename), detected_mime)
    logger.info(f"Extension validation passed for {_sanitize_log(str(document.filename))}")

    document.mime_type = detected_mime  # type: ignore[assignment]
    await session.flush()
    logger.info(f"Updated document.mime_type to {detected_mime}")


async def _extract_text(session: AsyncSession, job_id: UUID) -> None:
    """Execute document text extraction logic with idempotency deduplication.

    Checks idempotency key before extraction to skip work on retry.
    Extracts text from document, chunks it, and stores in DocumentExtraction.

    Args:
        session: AsyncSession for database access
        job_id: UUID of job to extract

    Raises:
        ExtractionError: If extraction fails
        ValueError: If document or file not found
    """
    settings = get_settings()
    job_repo = JobRepository()
    doc_repo = DocumentRepository()
    ext_repo = DocumentExtractionRepository()

    job = await job_repo.read(session, job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")

    doc_id = job.job_metadata.get("document_id") if job.job_metadata else None
    if not doc_id:
        raise ValueError(
            f"Job {job_id} has no document_id in metadata; "
            "document_id must be passed in job_metadata"
        )

    document = await doc_repo.read(session, UUID(doc_id))
    if not document:
        raise ValueError(f"Document {doc_id} not found")

    # Task 27: Generate idempotency key for deduplication
    job_metadata: dict[str, object] = (
        job.job_metadata if isinstance(job.job_metadata, dict) else {}
    )
    job_type_value = str(job.job_type) if job.job_type else job.job_type
    idempotency_key = generate_idempotency_key(
        document_id=document.id,
        job_type=job_type_value,
        job_metadata=job_metadata,
    )

    # Task 27: Check for cached extraction (cache hit = skip work)
    cached_extraction = await ext_repo.read_by_idempotency_key(session, idempotency_key)
    if cached_extraction:
        logger.info(
            f"[IDEMPOTENT] Cache HIT for job {job_id}: "
            f"using existing extraction (chunks={cached_extraction.chunk_count})"
        )
        return

    # Task 27: Log cache miss and start fresh extraction
    logger.info(
        f"[IDEMPOTENT] Cache MISS for job {job_id}: "
        f"starting fresh extraction (key={idempotency_key[:16]}...)"
    )

    storage_root = Path(settings.STORAGE_PATH).resolve()
    storage_path = (storage_root / document.storage_path).resolve()

    try:
        storage_path.relative_to(storage_root)
    except ValueError:
        raise ValueError(f"Document storage_path escapes storage root: {document.storage_path!r}")

    if not storage_path.exists():
        raise FileNotFoundError(f"File not found at {document.storage_path!r}")

    file_bytes = storage_path.read_bytes()
    logger.info(f"Loaded file for extraction: {_sanitize_log(str(document.storage_path))} ({len(file_bytes)} bytes)")

    mime_type = document.mime_type
    extracted_text = None
    page_count = None

    if mime_type == "application/pdf":
        extracted_text, page_count = extract_from_pdf(file_bytes)
    elif mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        extracted_text = extract_from_docx(file_bytes)
    elif mime_type == "text/csv":
        extracted_text = extract_from_csv(file_bytes)
    elif mime_type == "text/plain":
        extracted_text = extract_from_txt(file_bytes)
    elif mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        extracted_text = extract_from_xlsx(file_bytes)
    else:
        raise ExtractionError(f"Unsupported MIME type for extraction: {mime_type}")

    if not extracted_text or not extracted_text.strip():
        raise ExtractionError(f"No text extracted from document {document.id}")

    # Use TextChunker with default configuration
    chunker = TextChunker(
        chunk_size=1000, overlap=150, strategy="sentence_aware"
    )
    chunks = chunker.chunk(extracted_text, document_id=str(document.id))
    logger.info(
        f"Text extraction successful: {len(extracted_text)} chars, {len(chunks)} chunks"
    )

    extraction = DocumentExtraction(
        document_id=str(document.id),
        extracted_text=extracted_text,
        chunks=chunks,
        chunk_count=len(chunks),
        extraction_status="extracted",
        pages=page_count,
        idempotency_key=idempotency_key,
    )
    session.add(extraction)
    try:
        await session.flush()
    except IntegrityError as ie:
        await session.rollback()
        logger.warning(
            f"[IDEMPOTENT] Concurrent extraction detected for job {job_id}: "
            f"IntegrityError (likely concurrent insert with same key), reusing existing extraction"
        )
        cached_extraction = await ext_repo.read_by_idempotency_key(session, idempotency_key)
        if not cached_extraction:
            logger.error(
                f"[IDEMPOTENT] Failed to recover from concurrent extraction for job {job_id}: "
                "extraction not found after IntegrityError"
            )
            raise ExtractionError(
                f"Concurrent extraction failed for document {document.id}: {ie}"
            ) from ie
        return
    logger.info(
        f"[IDEMPOTENT] Extraction complete for job {job_id}: "
        f"stored with key={idempotency_key[:16]}... (chunks={len(chunks)})"
    )


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
        ExtractionError,
        ValueError,
        FileNotFoundError,
    ) as ve:
        # FIX #1: Validation and permanent errors: fail immediately, do NOT retry
        sanitized_error = _sanitize_log(str(ve))
        logger.warning(f"Permanent error for job {job_id}: {sanitized_error}")
        await _mark_job_failed(job_id, str(ve))
        return

    except Exception as e:
        # System errors: allow Celery to retry
        sanitized_error = _sanitize_log(str(e))
        logger.error(f"{action_name} for job {job_id} failed: {sanitized_error}", exc_info=True)
        await _mark_job_failed(job_id, str(e))
        raise


def _run_task(
    task_name: str,
    job_id: str,
    action_name: str,
    business_logic_fn=None,
    celery_task=None,
) -> None:
    """Sync wrapper for async job execution with DLQ integration.

    Args:
        task_name: Name of Celery task (for logging)
        job_id: UUID of job to process
        action_name: Name of action for logging
        business_logic_fn: Optional async function to execute
        celery_task: Celery task instance (with self.request.retries info)

    Raises:
        Exception: If action fails
    """
    try:
        asyncio.run(_run_job(job_id, action_name, business_logic_fn))
    except Exception as e:
        retry_count = celery_task.request.retries if celery_task else 0
        max_retries = celery_task.max_retries if celery_task else 3

        # Check if we WILL attempt a retry (retry_count < max_retries)
        # When retry_count == max_retries, we've exhausted all retries
        if retry_count < max_retries:
            log_retry_attempt(
                job_id=UUID(job_id),
                attempt_num=retry_count + 1,
                next_delay_seconds=2 ** (retry_count + 1),  # 2^n
            )
        else:
            # Max retries exhausted; move to DLQ
            sanitized_error = _sanitize_log(str(e))
            log_retry_exhausted(
                job_id=UUID(job_id),
                final_error=sanitized_error,
            )
            try:
                # Move to DLQ using existing event loop context
                async def run_dlq_move(error_msg: str):
                    dlq_session = await _get_session()
                    await _move_to_dlq_async(
                        dlq_session, UUID(job_id), error_msg, retry_count
                    )

                asyncio.run(run_dlq_move(str(e)))
            except Exception as dlq_error:
                sanitized_dlq_error = _sanitize_log(str(dlq_error))
                logger.error(
                    f"Failed to move job {job_id} to DLQ: {sanitized_dlq_error}",
                    exc_info=True,
                )

        sanitized_error = _sanitize_log(str(e))
        logger.error(f"{task_name} failed for job {job_id}: {sanitized_error}", exc_info=True)
        raise


# ===== Celery Tasks =====


@celery_app.task(
    bind=True,
    name="app.tasks.document_tasks.validate_document_task",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
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
        celery_task=self,
    )


@celery_app.task(
    bind=True,
    name="app.tasks.document_tasks.extract_text_task",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def extract_text_task(self, job_id: str) -> None:
    """Extract text from document and store in DocumentExtraction table.

    Workflow:
    1. Fetch Job and Document
    2. Load file from storage (validate path doesn't escape root)
    3. Determine format from Document.mime_type
    4. Call appropriate extractor (PDF/DOCX/CSV/XLSX/TXT)
    5. Chunk extracted text
    6. Create DocumentExtraction record
    7. Update Job status: pending → processing → completed/failed

    Args:
        job_id: UUID of Job tracking this extraction (string for JSON serialization)

    Error Handling:
    - Extraction errors: fail immediately, mark job as failed
    - System errors (DB, IO): retry up to 3 times
    """
    _run_task(
        "extract_text_task",
        job_id,
        "Extracting text from document",
        _extract_text,
        celery_task=self,
    )
