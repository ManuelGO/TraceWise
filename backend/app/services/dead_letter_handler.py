"""Dead-letter queue handler for permanent task failures."""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.document_extraction import DocumentExtractionRepository
from app.db.repositories.job import JobRepository
from app.utils.idempotency import generate_idempotency_key

logger = logging.getLogger(__name__)


async def move_to_dlq(
    session: AsyncSession,
    job_id: UUID,
    error_message: str,
    retry_count: int,
) -> None:
    """Move job to dead-letter queue after max retries exhausted.

    Updates job status to "failed" and logs context for manual review.
    If extraction exists for this job's idempotency key, logs and returns early
    to avoid duplicate escalation.

    Args:
        session: AsyncSession for database access
        job_id: UUID of job that exhausted retries
        error_message: Original error from final failure (truncated to 1000 chars)
        retry_count: Number of retries attempted

    Raises:
        ValueError: If job not found
    """
    job_repo = JobRepository()
    ext_repo = DocumentExtractionRepository()

    # Query job
    job = await job_repo.read(session, job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")

    # Check if extraction exists for this job (by idempotency_key)
    # If so, skip DLQ escalation; extraction succeeded despite retry count
    if job.job_metadata:
        job_metadata: dict[str, object] = (
            job.job_metadata if isinstance(job.job_metadata, dict) else {}
        )

        document_id_str = job_metadata.get("document_id")
        if not document_id_str:
            raise ValueError(f"Job {job_id}: missing document_id in metadata")

        try:
            document_id = UUID(str(document_id_str))
        except (ValueError, TypeError) as e:
            raise ValueError(f"Job {job_id}: invalid document_id format in metadata") from e

        idempotency_key = generate_idempotency_key(
            document_id=document_id,
            job_type=str(job.job_type) if job.job_type else "unknown",
            job_metadata=job_metadata,
        )
        cached_extraction = await ext_repo.read_by_idempotency_key(
            session, idempotency_key
        )
        if cached_extraction:
            logger.info(
                f"[DLQ] Job {job_id}: Extraction found despite max retries; "
                f"skipping DLQ escalation (extraction exists for key={idempotency_key[:16]}...)"
            )
            return

    # Truncate error message to 1000 characters for storage
    truncated_error = error_message[:1000] if error_message else "Unknown error"

    # Update job status to failed using domain method
    job.mark_failed(truncated_error)
    await session.flush()

    # Log DLQ event with context
    logger.warning(
        f"[DLQ] Job {job_id}: Max retries ({retry_count}) exhausted; "
        f"moved to DLQ for manual review. Error: {truncated_error}"
    )
