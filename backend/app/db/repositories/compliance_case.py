"""ComplianceCase repository for specialized data access patterns."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import BaseRepository
from app.models import CaseStatus, ComplianceCase


class ComplianceCaseRepository(BaseRepository[ComplianceCase]):
    """Repository for ComplianceCase with specialized query methods.

    Allowed filter fields:
    - status: Filter by case status (draft, processing, awaiting_review, approved, rejected, completed)
    - risk_level: Filter by risk level (low, medium, high, critical)

    Note: user_id/owner_id filtering deferred to Phase 3 with multi-user auth.
    """

    def __init__(self):
        """Initialize repository for ComplianceCase model."""
        super().__init__(ComplianceCase)
        # Define which fields can be filtered on
        self.FILTERABLE_FIELDS = {"status", "risk_level"}

    async def find_by_title(
        self, session: AsyncSession, title: str
    ) -> ComplianceCase | None:
        """Find a compliance case by title.

        Args:
            session: AsyncSession instance
            title: Case title to search for

        Returns:
            ComplianceCase instance if found, None otherwise
        """
        stmt = select(ComplianceCase).where(ComplianceCase.title == title)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_status(
        self,
        session: AsyncSession,
        status: CaseStatus,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ComplianceCase]:
        """Find all compliance cases with the given status.

        Args:
            session: AsyncSession instance
            status: CaseStatus to filter by
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of ComplianceCase instances matching the status
        """
        return await self.list_by_filter(
            session, skip=skip, limit=limit, status=status
        )

    async def find_active_cases(
        self, session: AsyncSession, skip: int = 0, limit: int = 100
    ) -> Any:
        """Find all active compliance cases (not DRAFT or COMPLETED).

        Args:
            session: AsyncSession instance
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of active ComplianceCase instances
        """
        stmt = (
            select(ComplianceCase)
            .where(
                ComplianceCase.status.notin_([CaseStatus.DRAFT, CaseStatus.COMPLETED])
            )
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()


__all__ = ["ComplianceCaseRepository"]
