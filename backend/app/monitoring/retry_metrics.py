"""Retry metrics and observability for task execution."""

import logging
from uuid import UUID

logger = logging.getLogger(__name__)


def _sanitize_log(text: str) -> str:
    """Sanitize text for safe logging (prevent log injection).

    Replaces newlines and carriage returns with spaces.
    """
    return text.replace("\n", " ").replace("\r", " ").replace("\x00", " ")


def log_retry_attempt(
    job_id: UUID,
    attempt_num: int,
    next_delay_seconds: float,
) -> None:
    """Log scheduled retry attempt with delay information.

    Args:
        job_id: UUID of job being retried
        attempt_num: Current attempt number (1-based)
        next_delay_seconds: Delay in seconds before next retry
    """
    logger.info(
        f"[RETRY] job_id={job_id} attempt={attempt_num} "
        f"next_delay={next_delay_seconds:.2f}s"
    )


def log_retry_exhausted(
    job_id: UUID,
    final_error: str,
) -> None:
    """Log when a job exhausts all retry attempts.

    Args:
        job_id: UUID of job that exhausted retries
        final_error: Error message from final failure
    """
    sanitized_error = _sanitize_log(final_error)
    logger.warning(
        f"[RETRY_EXHAUSTED] job_id={job_id} error={sanitized_error}"
    )
