"""Tests for dead-letter queue handler."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.dead_letter_handler import move_to_dlq


class TestDeadLetterHandler:
    """Test DLQ handler for permanent job failures."""

    @pytest.mark.asyncio
    async def test_move_to_dlq_updates_job_status(self):
        """Verify job status updated to failed when moved to DLQ."""
        job_id = uuid4()
        doc_id = uuid4()

        # Mock the repositories and session
        mock_job = MagicMock()
        mock_job.job_metadata = {"document_id": str(doc_id)}
        mock_job.mark_failed = MagicMock()

        mock_session = AsyncMock()

        with patch("app.services.dead_letter_handler.JobRepository") as mock_job_repo, \
             patch("app.services.dead_letter_handler.DocumentExtractionRepository") as mock_ext_repo:
            # Configure mocks
            mock_job_repo_instance = MagicMock()
            mock_job_repo_instance.read = AsyncMock(return_value=mock_job)
            mock_job_repo.return_value = mock_job_repo_instance

            mock_ext_repo_instance = MagicMock()
            mock_ext_repo_instance.read_by_idempotency_key = AsyncMock(
                return_value=None
            )
            mock_ext_repo.return_value = mock_ext_repo_instance

            # Call function
            await move_to_dlq(
                session=mock_session,
                job_id=job_id,
                error_message="Test error message",
                retry_count=3,
            )

            # Verify mark_failed was called with truncated error
            mock_job.mark_failed.assert_called_once_with("Test error message")
            assert mock_session.flush.called

    @pytest.mark.asyncio
    async def test_move_to_dlq_job_not_found(self):
        """Verify ValueError raised when job not found."""
        job_id = uuid4()

        mock_session = AsyncMock()

        with patch(
            "app.services.dead_letter_handler.JobRepository"
        ) as mock_job_repo:
            mock_job_repo_instance = MagicMock()
            mock_job_repo_instance.read = AsyncMock(return_value=None)
            mock_job_repo.return_value = mock_job_repo_instance

            with pytest.raises(ValueError, match=r"Job.*not found"):
                await move_to_dlq(
                    session=mock_session,
                    job_id=job_id,
                    error_message="Test error",
                    retry_count=3,
                )

    @pytest.mark.asyncio
    async def test_move_to_dlq_truncates_long_error_message(self):
        """Verify error message truncated to 1000 characters."""
        job_id = uuid4()

        mock_job = MagicMock()
        mock_job.job_metadata = None
        mock_job.mark_failed = MagicMock()
        mock_session = AsyncMock()

        long_error = "x" * 2000

        with patch("app.services.dead_letter_handler.JobRepository") as mock_job_repo, \
             patch("app.services.dead_letter_handler.DocumentExtractionRepository") as mock_ext_repo:
            mock_job_repo_instance = MagicMock()
            mock_job_repo_instance.read = AsyncMock(return_value=mock_job)
            mock_job_repo.return_value = mock_job_repo_instance

            mock_ext_repo_instance = MagicMock()
            mock_ext_repo_instance.read_by_idempotency_key = AsyncMock(
                return_value=None
            )
            mock_ext_repo.return_value = mock_ext_repo_instance

            await move_to_dlq(
                session=mock_session,
                job_id=job_id,
                error_message=long_error,
                retry_count=3,
            )

            # Verify mark_failed was called with truncated error (max 1000 chars)
            mock_job.mark_failed.assert_called_once()
            truncated_msg = mock_job.mark_failed.call_args[0][0]
            assert len(truncated_msg) == 1000
            assert truncated_msg == "x" * 1000

    @pytest.mark.asyncio
    async def test_move_to_dlq_with_empty_error_message(self):
        """Verify handling of empty error message."""
        job_id = uuid4()

        mock_job = MagicMock()
        mock_job.job_metadata = None
        mock_job.mark_failed = MagicMock()
        mock_session = AsyncMock()

        with patch("app.services.dead_letter_handler.JobRepository") as mock_job_repo, \
             patch("app.services.dead_letter_handler.DocumentExtractionRepository") as mock_ext_repo:
            mock_job_repo_instance = MagicMock()
            mock_job_repo_instance.read = AsyncMock(return_value=mock_job)
            mock_job_repo.return_value = mock_job_repo_instance

            mock_ext_repo_instance = MagicMock()
            mock_ext_repo_instance.read_by_idempotency_key = AsyncMock(
                return_value=None
            )
            mock_ext_repo.return_value = mock_ext_repo_instance

            await move_to_dlq(
                session=mock_session,
                job_id=job_id,
                error_message="",
                retry_count=3,
            )

            # Verify default message
            mock_job.mark_failed.assert_called_once_with("Unknown error")

    @pytest.mark.asyncio
    async def test_move_to_dlq_with_no_metadata(self):
        """Verify DLQ handler works with jobs that have no metadata."""
        job_id = uuid4()

        mock_job = MagicMock()
        mock_job.job_metadata = None
        mock_job.mark_failed = MagicMock()
        mock_session = AsyncMock()

        with patch("app.services.dead_letter_handler.JobRepository") as mock_job_repo, \
             patch("app.services.dead_letter_handler.DocumentExtractionRepository"):
            mock_job_repo_instance = MagicMock()
            mock_job_repo_instance.read = AsyncMock(return_value=mock_job)
            mock_job_repo.return_value = mock_job_repo_instance

            # Should not raise error
            await move_to_dlq(
                session=mock_session,
                job_id=job_id,
                error_message="Test error",
                retry_count=3,
            )

            mock_job.mark_failed.assert_called_once_with("Test error")

    @pytest.mark.asyncio
    async def test_move_to_dlq_missing_document_id(self):
        """Verify ValueError raised when document_id missing from metadata."""
        job_id = uuid4()

        mock_job = MagicMock()
        mock_job.job_metadata = {"other_field": "value"}  # No document_id
        mock_session = AsyncMock()

        with patch("app.services.dead_letter_handler.JobRepository") as mock_job_repo:
            mock_job_repo_instance = MagicMock()
            mock_job_repo_instance.read = AsyncMock(return_value=mock_job)
            mock_job_repo.return_value = mock_job_repo_instance

            with pytest.raises(ValueError, match="missing document_id"):
                await move_to_dlq(
                    session=mock_session,
                    job_id=job_id,
                    error_message="Test error",
                    retry_count=3,
                )
