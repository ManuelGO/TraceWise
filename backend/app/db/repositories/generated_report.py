"""GeneratedReport repository for specialized data access patterns."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import BaseRepository
from app.models import GeneratedReport


class GeneratedReportRepository(BaseRepository[GeneratedReport]):
    """Repository for GeneratedReport with specialized query methods.

    Allowed filter fields:
    - case_id: Filter by parent compliance case
    - report_type: Filter by report type (compliance_summary, risk_analysis, etc.)
    """

    def __init__(self):
        """Initialize repository for GeneratedReport model."""
        super().__init__(GeneratedReport)
        # Define which fields can be filtered on
        self.FILTERABLE_FIELDS = {"case_id", "report_type"}

    async def find_by_case_id(
        self,
        session: AsyncSession,
        case_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[GeneratedReport]:
        """Find all generated reports for a given compliance case.

        Args:
            session: AsyncSession instance
            case_id: ComplianceCase ID to search for
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of GeneratedReport instances for the given case
        """
        return await self.list_by_filter(session, skip=skip, limit=limit, case_id=case_id)

    async def find_by_report_type(
        self,
        session: AsyncSession,
        report_type: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[GeneratedReport]:
        """Find all reports of a specific type.

        Args:
            session: AsyncSession instance
            report_type: Type of report to filter by
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of GeneratedReport instances of the given type
        """
        return await self.list_by_filter(session, skip=skip, limit=limit, report_type=report_type)

    async def find_latest_reports(
        self,
        session: AsyncSession,
        case_id: UUID,
        limit: int = 10,
    ) -> Any:
        """Find the latest generated reports for a case.

        Args:
            session: AsyncSession instance
            case_id: ComplianceCase ID to search for
            limit: Maximum number of recent reports to return

        Returns:
            List of most recent GeneratedReport instances for the case
        """
        from sqlalchemy import select

        stmt = (
            select(GeneratedReport)
            .where(GeneratedReport.case_id == case_id)
            .order_by(GeneratedReport.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()


__all__ = ["GeneratedReportRepository"]
