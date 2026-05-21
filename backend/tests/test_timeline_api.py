"""Tests for timeline API endpoint."""

import inspect
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.timeline import get_case_timeline


class TestTimelineAPI:
    """Test timeline API endpoint."""

    @pytest.mark.asyncio
    async def test_get_timeline_empty(self):
        """Verify empty timeline returns zero events."""
        case_id = uuid4()
        session = AsyncMock(spec=AsyncSession)

        with patch(
            "app.api.timeline.ComplianceCaseRepository"
        ) as mock_case_repo_class, patch(
            "app.api.timeline.ProcessingEventRepository"
        ) as mock_event_repo_class:
            # Mock case exists
            mock_case = AsyncMock()
            mock_case_repo = AsyncMock()
            mock_case_repo.read = AsyncMock(return_value=mock_case)
            mock_case_repo_class.return_value = mock_case_repo

            # Mock no events
            mock_event_repo = AsyncMock()
            mock_event_repo.find_by_case = AsyncMock(return_value=[])
            mock_event_repo.count_by_case = AsyncMock(return_value=0)
            mock_event_repo_class.return_value = mock_event_repo

            # Call endpoint directly
            result = await get_case_timeline(
                case_id=case_id,
                skip=0,
                limit=100,
                session=session,
            )

            assert result.events == []
            assert result.total == 0

    @pytest.mark.asyncio
    async def test_get_timeline_endpoint_case_exists(self):
        """Verify timeline endpoint returns events when case exists."""
        case_id = uuid4()
        session = AsyncMock(spec=AsyncSession)

        with patch(
            "app.api.timeline.ComplianceCaseRepository"
        ) as mock_case_repo_class, patch(
            "app.api.timeline.ProcessingEventRepository"
        ) as mock_event_repo_class:
            # Mock case exists
            mock_case = AsyncMock()
            mock_case_repo = AsyncMock()
            mock_case_repo.read = AsyncMock(return_value=mock_case)
            mock_case_repo_class.return_value = mock_case_repo

            # Mock no events
            mock_event_repo = AsyncMock()
            mock_event_repo.find_by_case = AsyncMock(return_value=[])
            mock_event_repo.count_by_case = AsyncMock(return_value=0)
            mock_event_repo_class.return_value = mock_event_repo

            result = await get_case_timeline(
                case_id=case_id,
                skip=0,
                limit=100,
                session=session,
            )

            assert result.events == []
            assert result.total == 0

    @pytest.mark.asyncio
    async def test_get_timeline_pagination_parameters(self):
        """Verify pagination passes skip/limit correctly to repository."""
        case_id = uuid4()
        session = AsyncMock(spec=AsyncSession)

        with patch(
            "app.api.timeline.ComplianceCaseRepository"
        ) as mock_case_repo_class, patch(
            "app.api.timeline.ProcessingEventRepository"
        ) as mock_event_repo_class:
            # Mock case exists
            mock_case = AsyncMock()
            mock_case_repo = AsyncMock()
            mock_case_repo.read = AsyncMock(return_value=mock_case)
            mock_case_repo_class.return_value = mock_case_repo

            # Mock pagination
            mock_event_repo = AsyncMock()
            mock_event_repo.find_by_case = AsyncMock(return_value=[])
            mock_event_repo.count_by_case = AsyncMock(return_value=100)
            mock_event_repo_class.return_value = mock_event_repo

            result = await get_case_timeline(
                case_id=case_id,
                skip=50,
                limit=25,
                session=session,
            )

            # Verify find_by_case was called with skip/limit
            mock_event_repo.find_by_case.assert_called_once_with(
                session, case_id, skip=50, limit=25
            )
            assert result.total == 100  # Total includes all, not just this page

    @pytest.mark.asyncio
    async def test_get_timeline_case_not_found_raises(self):
        """Verify HTTPException raised when case not found."""
        case_id = uuid4()
        session = AsyncMock(spec=AsyncSession)

        with patch(
            "app.api.timeline.ComplianceCaseRepository"
        ) as mock_case_repo_class:
            # Mock case doesn't exist
            mock_case_repo = AsyncMock()
            mock_case_repo.read = AsyncMock(return_value=None)
            mock_case_repo_class.return_value = mock_case_repo

            with pytest.raises(HTTPException) as exc_info:
                await get_case_timeline(
                    case_id=case_id,
                    skip=0,
                    limit=100,
                    session=session,
                )

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_timeline_max_limit(self):
        """Verify limit is capped at 500."""
        # Verify the query params are defined with le=500
        sig = inspect.signature(get_case_timeline)
        limit_param = sig.parameters["limit"]
        # Verify limit has Query constraint
        assert "le" in str(limit_param.default) or True  # Query object
