"""Persistence service for consistency check results."""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consistency_check import ConsistencyCheck
from app.schemas.consistency import ConsistencyReport

logger = logging.getLogger(__name__)


class ConsistencyService:
    """Service for persisting and retrieving consistency check results."""

    async def save_report(
        self,
        session: AsyncSession,
        case_id: UUID,
        report: ConsistencyReport,
    ) -> ConsistencyCheck:
        """Save a consistency report to the database.

        WARNING: Caller must ensure session is within active transaction.
        Best practice: wrap in `async with session.begin():` before calling.

        Args:
            session: Database session (must be within active transaction)
            case_id: Case ID
            report: Consistency report to save

        Returns:
            Saved ConsistencyCheck model instance
        """
        # Calculate severity distribution
        severity_dist = {
            "high": 0,
            "medium": 0,
            "low": 0,
        }

        # Count by severity
        for conflict in (
            report.field_conflicts + report.temporal_conflicts + report.logical_conflicts
        ):
            severity = conflict.severity.value.lower()
            if severity in severity_dist:
                severity_dist[severity] += 1

        # Create model instance
        check = ConsistencyCheck(
            case_id=case_id,
            report_data=report.model_dump(mode="json"),
            conflicts_count=report.total_conflict_count,
            severity_distribution=severity_dist,
        )

        # Save to database
        session.add(check)
        await session.flush()

        logger.info(
            f"Saved consistency check for case {case_id}: "
            f"{report.total_conflict_count} conflicts detected"
        )

        return check

    async def get_report(
        self,
        session: AsyncSession,
        case_id: UUID,
    ) -> ConsistencyCheck | None:
        """Retrieve the latest consistency report for a case.

        Args:
            session: Database session
            case_id: Case ID

        Returns:
            ConsistencyCheck instance or None if not found
        """
        stmt = (
            select(ConsistencyCheck)
            .where(ConsistencyCheck.case_id == case_id)
            .order_by(ConsistencyCheck.created_at.desc())
            .limit(1)
        )

        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_reports_for_case(
        self,
        session: AsyncSession,
        case_id: UUID,
        limit: int = 10,
    ) -> list[ConsistencyCheck]:
        """Retrieve all consistency reports for a case.

        Args:
            session: Database session
            case_id: Case ID
            limit: Maximum number of reports to return (clamped to [1, 100])

        Returns:
            List of ConsistencyCheck instances
        """
        # Clamp limit to prevent unbounded result sets
        limit = min(max(limit, 1), 100)

        stmt = (
            select(ConsistencyCheck)
            .where(ConsistencyCheck.case_id == case_id)
            .order_by(ConsistencyCheck.created_at.desc())
            .limit(limit)
        )

        result = await session.execute(stmt)
        return list(result.scalars().all())
