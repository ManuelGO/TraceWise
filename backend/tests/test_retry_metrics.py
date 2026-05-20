"""Tests for retry metrics and observability."""

import logging
from uuid import uuid4

import pytest

from app.monitoring.retry_metrics import log_retry_attempt, log_retry_exhausted


class TestRetryMetrics:
    """Test retry metrics logging and observability."""

    def test_log_retry_attempt_format(self, caplog):
        """Verify retry attempt log has correct format."""
        job_id = uuid4()

        with caplog.at_level(logging.INFO):
            log_retry_attempt(
                job_id=job_id,
                attempt_num=1,
                next_delay_seconds=2.5,
            )

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.levelname == "INFO"
        assert "[RETRY]" in record.message
        assert str(job_id) in record.message
        assert "attempt=1" in record.message
        assert "next_delay=2.50s" in record.message

    def test_log_retry_attempt_multiple_attempts(self, caplog):
        """Verify retry metrics logged for multiple attempts."""
        job_id = uuid4()

        with caplog.at_level(logging.INFO):
            for attempt in range(1, 4):
                delay = 2 ** attempt
                log_retry_attempt(
                    job_id=job_id,
                    attempt_num=attempt,
                    next_delay_seconds=float(delay),
                )

        assert len(caplog.records) == 3
        assert all(r.levelname == "INFO" for r in caplog.records)
        assert "attempt=1" in caplog.records[0].message
        assert "attempt=2" in caplog.records[1].message
        assert "attempt=3" in caplog.records[2].message

    def test_log_retry_exhausted_format(self, caplog):
        """Verify retry exhausted log has correct format."""
        job_id = uuid4()
        error = "FileSizeTooLargeError: exceeds 50MB"

        with caplog.at_level(logging.WARNING):
            log_retry_exhausted(
                job_id=job_id,
                final_error=error,
            )

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.levelname == "WARNING"
        assert "[RETRY_EXHAUSTED]" in record.message
        assert str(job_id) in record.message
        assert error in record.message

    def test_log_retry_exhausted_with_long_error(self, caplog):
        """Verify retry exhausted handles long error messages."""
        job_id = uuid4()
        long_error = "x" * 500  # Long error message

        with caplog.at_level(logging.WARNING):
            log_retry_exhausted(
                job_id=job_id,
                final_error=long_error,
            )

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.levelname == "WARNING"
        assert long_error in record.message

    def test_log_retry_attempt_with_small_delay(self, caplog):
        """Verify retry attempt with small delay (first retry)."""
        job_id = uuid4()

        with caplog.at_level(logging.INFO):
            log_retry_attempt(
                job_id=job_id,
                attempt_num=1,
                next_delay_seconds=2.0,
            )

        record = caplog.records[0]
        assert "next_delay=2.00s" in record.message

    def test_log_retry_attempt_with_large_delay(self, caplog):
        """Verify retry attempt with large delay (capped at 600s)."""
        job_id = uuid4()

        with caplog.at_level(logging.INFO):
            log_retry_attempt(
                job_id=job_id,
                attempt_num=10,
                next_delay_seconds=600.0,
            )

        record = caplog.records[0]
        assert "next_delay=600.00s" in record.message

    def test_log_retry_attempt_with_fractional_delay(self, caplog):
        """Verify retry attempt with fractional delay (includes jitter)."""
        job_id = uuid4()

        with caplog.at_level(logging.INFO):
            log_retry_attempt(
                job_id=job_id,
                attempt_num=2,
                next_delay_seconds=3.7,  # Delay with jitter
            )

        record = caplog.records[0]
        assert "next_delay=3.70s" in record.message
