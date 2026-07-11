"""WorkflowStateCheckpoint repository for compliance-workflow state persistence (Task 52)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import BaseRepository
from app.models import WorkflowStateCheckpoint


class WorkflowStateRepository(BaseRepository[WorkflowStateCheckpoint]):
    """Repository for ``WorkflowStateCheckpoint`` with run/case-scoped query methods.

    Allowed filter fields:
    - ``run_id``: all checkpoints of one workflow run.
    - ``case_id``: all checkpoints for a compliance case (audit trail).
    - ``step``: checkpoints recorded after a given workflow node.
    - ``status``: ``in_progress`` | ``completed`` | ``failed``.
    """

    def __init__(self):
        """Initialize repository for the WorkflowStateCheckpoint model."""
        super().__init__(WorkflowStateCheckpoint)
        self.FILTERABLE_FIELDS = {"run_id", "case_id", "step", "status"}

    async def find_by_run_id(
        self,
        session: AsyncSession,
        run_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[WorkflowStateCheckpoint]:
        """Find all checkpoints of one workflow run, oldest-first (the ordered audit trail).

        Args:
            session: AsyncSession instance.
            run_id: The workflow run identifier.
            skip: Number of records to skip.
            limit: Maximum number of records to return (capped at 1000).

        Returns:
            The run's checkpoints ordered by ``created_at`` ascending.
        """
        limit = min(limit, 1000)
        stmt = (
            select(WorkflowStateCheckpoint)
            .where(WorkflowStateCheckpoint.run_id == run_id)
            .order_by(WorkflowStateCheckpoint.created_at.asc())
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def find_latest_by_run_id(
        self,
        session: AsyncSession,
        run_id: UUID,
    ) -> WorkflowStateCheckpoint | None:
        """Find the newest checkpoint of a workflow run (the recovery entry point).

        Args:
            session: AsyncSession instance.
            run_id: The workflow run identifier.

        Returns:
            The most recent ``WorkflowStateCheckpoint`` for the run, or ``None`` if it has none.
        """
        # TODO(post-launch, FIX 3): ``created_at`` is a Python-side ``datetime.now(UTC)`` set per row
        # with no secondary sort key, so two checkpoints written in the same sub-millisecond window
        # (rare -- each has a real DB round-trip between them -- but possible) tie, and Postgres does
        # not guarantee a stable tiebreak. On a tie this could return a not-actually-latest row. The
        # durable fix is a monotonic tiebreaker (a DB-generated autoincrement ``sequence`` column,
        # ordering by ``(created_at, sequence)``), which needs a migration -- deferred as post-launch
        # hardening (low probability, does not block the MVP).
        stmt = (
            select(WorkflowStateCheckpoint)
            .where(WorkflowStateCheckpoint.run_id == run_id)
            .order_by(WorkflowStateCheckpoint.created_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_case_id(
        self,
        session: AsyncSession,
        case_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[WorkflowStateCheckpoint]:
        """Find all checkpoints for a compliance case (across all its runs).

        Args:
            session: AsyncSession instance.
            case_id: ComplianceCase ID to search for.
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            The case's checkpoints (filtered by ``case_id``).
        """
        return await self.list_by_filter(session, skip=skip, limit=limit, case_id=case_id)


__all__ = ["WorkflowStateRepository"]
