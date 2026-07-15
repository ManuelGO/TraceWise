"""ReviewDecision repository for specialized data access patterns."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import BaseRepository
from app.models import ReviewDecision, ReviewDecisionType


class ReviewDecisionRepository(BaseRepository[ReviewDecision]):
    """Repository for ReviewDecision with specialized query methods.

    Allowed filter fields:
    - case_id: Filter by parent compliance case
    - decision: Filter by decision type (approved, rejected, needs_more_evidence, override)

    Note: ReviewDecision is an immutable audit record. Insecure to allow direct field
    updates. Only allow creation and read access for compliance auditing.
    """

    def __init__(self):
        """Initialize repository for ReviewDecision model."""
        super().__init__(ReviewDecision)
        # Define which fields can be filtered on. The model column is ``decision`` (not
        # ``decision_type``); a prior mismatch made ``find_by_decision_type`` raise
        # AttributeError at query-build time (Task 53 fix).
        self.FILTERABLE_FIELDS = {"case_id", "decision"}

    async def find_by_case_id(
        self,
        session: AsyncSession,
        case_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ReviewDecision]:
        """Find all review decisions for a given compliance case, newest-first.

        Args:
            session: AsyncSession instance
            case_id: ComplianceCase ID to search for
            skip: Number of records to skip
            limit: Maximum number of records to return (capped at 1000)

        Returns:
            List of ReviewDecision instances for the given case, ordered by ``created_at``
            descending (most recent decision first -- the audit trail read order).
        """
        limit = min(limit, 1000)
        stmt = (
            select(ReviewDecision)
            .where(ReviewDecision.case_id == case_id)
            # ``id`` is a secondary sort key so pages are stable when two rows share a
            # ``created_at`` (it is a Python-side ``datetime.now(UTC)`` default, so sub-ms ties
            # are possible); without it, tied rows could be skipped/duplicated across pages.
            .order_by(ReviewDecision.created_at.desc(), ReviewDecision.id.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_case_id(self, session: AsyncSession, case_id: UUID) -> int:
        """Count the review decisions recorded for a compliance case.

        Args:
            session: AsyncSession instance
            case_id: ComplianceCase ID to count decisions for

        Returns:
            The number of ReviewDecision rows for the case.
        """
        return await self.count_by_filter(session, case_id=case_id)

    async def find_by_decision_type(
        self,
        session: AsyncSession,
        decision_type: ReviewDecisionType,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ReviewDecision]:
        """Find all review decisions of a specific type.

        Args:
            session: AsyncSession instance
            decision_type: ReviewDecisionType to filter by
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of ReviewDecision instances of the given type
        """
        return await self.list_by_filter(
            session, skip=skip, limit=limit, decision=decision_type
        )

    async def find_approved_decisions(
        self, session: AsyncSession, skip: int = 0, limit: int = 100
    ) -> list[ReviewDecision]:
        """Find all approved review decisions.

        Args:
            session: AsyncSession instance
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of approved ReviewDecision instances
        """
        return await self.find_by_decision_type(
            session, ReviewDecisionType.APPROVED, skip=skip, limit=limit
        )

    async def find_rejected_decisions(
        self, session: AsyncSession, skip: int = 0, limit: int = 100
    ) -> list[ReviewDecision]:
        """Find all rejected review decisions.

        Args:
            session: AsyncSession instance
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of rejected ReviewDecision instances
        """
        return await self.find_by_decision_type(
            session, ReviewDecisionType.REJECTED, skip=skip, limit=limit
        )


__all__ = ["ReviewDecisionRepository"]
