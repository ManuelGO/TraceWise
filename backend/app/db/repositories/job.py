"""Job repository for specialized data access patterns."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import BaseRepository
from app.models import Job, JobStatus


class JobRepository(BaseRepository[Job]):
    """Repository for Job with specialized query methods.

    Allowed filter fields:
    - case_id: Filter by compliance case UUID
    - status: Filter by job status (pending, processing, completed, failed)
    - job_type: Filter by job type (extract_text, generate_embeddings, extract_entities, risk_assessment, generate_report)
    """

    def __init__(self):
        """Initialize repository for Job model."""
        super().__init__(Job)
        self.FILTERABLE_FIELDS = {"case_id", "status", "job_type"}

    async def find_by_case(
        self,
        session: AsyncSession,
        case_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Job]:
        """Find all jobs for a specific compliance case.

        Args:
            session: AsyncSession instance
            case_id: UUID of the compliance case
            skip: Number of records to skip (default 0)
            limit: Maximum number of records to return (default 100)

        Returns:
            List of Job instances for the specified case
        """
        return await self.list_by_filter(session, skip=skip, limit=limit, case_id=case_id)

    async def find_pending_jobs(
        self,
        session: AsyncSession,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Job]:
        """Find all jobs with pending status.

        Args:
            session: AsyncSession instance
            skip: Number of records to skip (default 0)
            limit: Maximum number of records to return (default 100)

        Returns:
            List of Job instances with status='pending'
        """
        return await self.list_by_filter(
            session, skip=skip, limit=limit, status=JobStatus.PENDING
        )


__all__ = ["JobRepository"]
