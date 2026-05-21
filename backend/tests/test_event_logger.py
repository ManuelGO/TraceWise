"""Tests for event logger service."""

import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.event_logger import ALLOWED_EVENT_TYPES, log_event


class TestEventLogger:
    """Test event logger service."""

    @pytest.mark.asyncio
    async def test_log_event_creates_correct_record(self):
        """Verify log_event creates record with correct schema."""
        case_id = uuid4()
        session = AsyncMock(spec=AsyncSession)

        event = await log_event(
            session=session,
            case_id=case_id,
            event_type="document_uploaded",
            metadata={"document_id": str(uuid4()), "filename": "test.pdf"},
        )

        assert event.case_id == case_id
        assert event.event_type == "document_uploaded"
        assert event.event_metadata == {"document_id": event.event_metadata["document_id"], "filename": "test.pdf"}
        assert session.add.called
        assert session.flush.called

    @pytest.mark.asyncio
    async def test_log_event_sets_utc_timestamp(self):
        """Verify log_event sets timestamp to UTC now by default."""
        case_id = uuid4()
        session = AsyncMock(spec=AsyncSession)
        before = datetime.now(UTC)

        event = await log_event(
            session=session,
            case_id=case_id,
            event_type="validation_started",
        )

        after = datetime.now(UTC)
        assert before <= event.timestamp <= after
        assert event.timestamp.tzinfo is not None

    @pytest.mark.asyncio
    async def test_log_event_accepts_explicit_timestamp(self):
        """Verify log_event accepts explicit timestamp override."""
        case_id = uuid4()
        session = AsyncMock(spec=AsyncSession)
        explicit_time = datetime(2026, 5, 20, 10, 30, 0, tzinfo=UTC)

        event = await log_event(
            session=session,
            case_id=case_id,
            event_type="extraction_completed",
            timestamp=explicit_time,
        )

        assert event.timestamp == explicit_time

    @pytest.mark.asyncio
    async def test_log_event_truncates_error_message(self):
        """Verify error_message truncated to 1000 chars."""
        case_id = uuid4()
        session = AsyncMock(spec=AsyncSession)
        long_error = "x" * 2000

        event = await log_event(
            session=session,
            case_id=case_id,
            event_type="validation_failed",
            metadata={"error_message": long_error},
        )

        assert len(event.event_metadata["error_message"]) == 1000
        assert event.event_metadata["error_message"] == "x" * 1000

    @pytest.mark.asyncio
    async def test_log_event_accepts_empty_metadata(self):
        """Verify log_event handles empty metadata."""
        case_id = uuid4()
        session = AsyncMock(spec=AsyncSession)

        event = await log_event(
            session=session,
            case_id=case_id,
            event_type="retry_scheduled",
            metadata={},
        )

        assert event.event_metadata == {}

    @pytest.mark.asyncio
    async def test_log_event_accepts_none_metadata(self):
        """Verify log_event accepts None metadata (converts to {})."""
        case_id = uuid4()
        session = AsyncMock(spec=AsyncSession)

        event = await log_event(
            session=session,
            case_id=case_id,
            event_type="max_retries_exceeded",
            metadata=None,
        )

        assert event.event_metadata == {}

    @pytest.mark.asyncio
    async def test_log_event_logs_unknown_event_type(self, caplog):
        """Verify unknown event_type logged at INFO level but accepted."""
        case_id = uuid4()
        session = AsyncMock(spec=AsyncSession)

        with caplog.at_level(logging.INFO):
            event = await log_event(
                session=session,
                case_id=case_id,
                event_type="unknown_event_type",
            )

        assert event.event_type == "unknown_event_type"
        assert "Unknown event_type" in caplog.text

    @pytest.mark.asyncio
    async def test_log_event_preserves_metadata_json(self):
        """Verify metadata JSONB round-trips correctly."""
        case_id = uuid4()
        session = AsyncMock(spec=AsyncSession)
        metadata = {
            "job_id": str(uuid4()),
            "chunk_count": 42,
            "pages": 10,
            "nested": {"key": "value", "list": [1, 2, 3]},
        }

        event = await log_event(
            session=session,
            case_id=case_id,
            event_type="extraction_completed",
            metadata=metadata,
        )

        assert event.event_metadata == metadata

    @pytest.mark.asyncio
    async def test_allowed_event_types_defined(self):
        """Verify allowed event types are defined."""
        expected_types = {
            "document_uploaded",
            "validation_started",
            "validation_completed",
            "validation_failed",
            "extraction_started",
            "extraction_completed",
            "extraction_failed",
            "retry_scheduled",
            "max_retries_exceeded",
        }
        assert ALLOWED_EVENT_TYPES == expected_types
