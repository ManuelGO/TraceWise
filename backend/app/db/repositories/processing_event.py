"""ProcessingEventRepository for specialized data access patterns."""

from typing import ClassVar
from uuid import UUID

from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import BaseRepository
from app.models import ProcessingEvent


class ProcessingEventRepository(BaseRepository[ProcessingEvent]):
    """Repository for ProcessingEvent with specialized query methods.

    Allowed filter fields:
    - case_id: Filter by compliance case UUID
    - event_type: Filter by event type (document_uploaded, validation_started, etc.)
    """

    FILTERABLE_FIELDS: ClassVar[set[str]] = {"case_id", "event_type"}

    def __init__(self):
        """Initialize repository for ProcessingEvent model."""
        super().__init__(ProcessingEvent)

    async def find_by_case(
        self,
        session: AsyncSession,
        case_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ProcessingEvent]:
        """Find all events for a specific compliance case, ordered by timestamp (earliest first).

        Args:
            session: AsyncSession instance
            case_id: UUID of the compliance case
            skip: Number of records to skip (default 0)
            limit: Maximum number of records to return (default 100)

        Returns:
            List of ProcessingEvent instances for the specified case, ordered by timestamp ascending
        """
        stmt = (
            select(self.model)
            .where(self.model.case_id == case_id)
            .order_by(asc(self.model.timestamp))
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_case(
        self,
        session: AsyncSession,
        case_id: UUID,
    ) -> int:
        """Count total events for a specific compliance case.

        Args:
            session: AsyncSession instance
            case_id: UUID of the compliance case

        Returns:
            Total number of ProcessingEvent instances for the specified case
        """
        return await self.count_by_filter(session, **{"case_id": case_id})

    async def count_all(
        self,
        session: AsyncSession,
    ) -> int:
        """Count all events across all cases (for metrics/testing).

        Args:
            session: AsyncSession instance

        Returns:
            Total number of ProcessingEvent instances
        """
        return await self.count(session)


__all__ = ["ProcessingEventRepository"]
