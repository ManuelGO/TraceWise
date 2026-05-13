"""RiskAssessment repository for specialized data access patterns."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import BaseRepository
from app.models import RiskAssessment, RiskLevel


class RiskAssessmentRepository(BaseRepository[RiskAssessment]):
    """Repository for RiskAssessment with specialized query methods.

    Allowed filter fields:
    - case_id: Filter by parent compliance case
    - risk_level: Filter by risk level (low, medium, high, critical)
    """

    def __init__(self):
        """Initialize repository for RiskAssessment model."""
        super().__init__(RiskAssessment)
        # Define which fields can be filtered on
        self.FILTERABLE_FIELDS = {"case_id", "risk_level"}

    async def find_by_case_id(
        self,
        session: AsyncSession,
        case_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[RiskAssessment]:
        """Find all risk assessments for a given compliance case.

        Args:
            session: AsyncSession instance
            case_id: ComplianceCase ID to search for
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of RiskAssessment instances for the given case
        """
        return await self.list_by_filter(session, skip=skip, limit=limit, case_id=case_id)

    async def find_by_risk_level(
        self,
        session: AsyncSession,
        risk_level: RiskLevel,
        skip: int = 0,
        limit: int = 100,
    ) -> list[RiskAssessment]:
        """Find all risk assessments with the given risk level.

        Args:
            session: AsyncSession instance
            risk_level: RiskLevel to filter by
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of RiskAssessment instances with the given risk level
        """
        return await self.list_by_filter(session, skip=skip, limit=limit, risk_level=risk_level)

    async def find_high_risk_assessments(
        self, session: AsyncSession, skip: int = 0, limit: int = 100
    ) -> list[RiskAssessment]:
        """Find all high-risk assessments.

        Args:
            session: AsyncSession instance
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of high-risk RiskAssessment instances
        """
        return await self.find_by_risk_level(session, RiskLevel.HIGH, skip=skip, limit=limit)


__all__ = ["RiskAssessmentRepository"]
