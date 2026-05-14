"""Integration tests for Job model persistence and state transitions.

Note: These tests require a live PostgreSQL database and are skipped in CI
where database isolation may not be available. Run locally with:
  pytest tests/test_job_persistence.py -m integration
"""

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.job import JobRepository
from app.models import CaseStatus, ComplianceCase, Job, JobStatus, JobType, RiskLevel

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION_TESTS"),
    reason="Integration tests require RUN_INTEGRATION_TESTS env var",
)


@pytest_asyncio.fixture
async def compliance_case(db_session: AsyncSession) -> ComplianceCase:
    """Create a test compliance case."""
    case = ComplianceCase(
        title=f"Test Case {uuid4()}",
        supplier_name="Test Supplier",
        product_type="Electronics",
        country_of_origin="USA",
        status=CaseStatus.DRAFT,
        risk_level=RiskLevel.MEDIUM,
    )
    db_session.add(case)
    await db_session.flush()
    return case


@pytest.mark.integration
class TestJobPersistence:
    """Tests for Job model persistence."""

    async def test_create_and_retrieve_job(
        self, db_session: AsyncSession, compliance_case: ComplianceCase
    ):
        """Test creating a job and retrieving it from database."""
        job = Job(
            case_id=compliance_case.id,
            job_type=JobType.EXTRACT_TEXT,
            job_metadata={"config": "value"},
        )
        db_session.add(job)
        await db_session.flush()

        retrieved = await db_session.get(Job, job.id)
        assert retrieved is not None
        assert retrieved.case_id == compliance_case.id
        assert retrieved.job_type == JobType.EXTRACT_TEXT
        assert retrieved.status == JobStatus.PENDING
        assert retrieved.job_metadata == {"config": "value"}

    async def test_job_state_transitions_persist(
        self, db_session: AsyncSession, compliance_case: ComplianceCase
    ):
        """Test that job state transitions persist to database."""
        job = Job(case_id=compliance_case.id, job_type=JobType.GENERATE_EMBEDDINGS)
        db_session.add(job)
        await db_session.flush()
        job_id = job.id

        job.mark_processing()
        await db_session.flush()

        retrieved = await db_session.get(Job, job_id)
        assert retrieved.status == JobStatus.PROCESSING
        assert retrieved.started_at is not None

        retrieved.mark_completed()
        await db_session.flush()

        final = await db_session.get(Job, job_id)
        assert final.status == JobStatus.COMPLETED
        assert final.completed_at is not None

    async def test_job_failure_persists_error_message(
        self, db_session: AsyncSession, compliance_case: ComplianceCase
    ):
        """Test that error messages are persisted when job fails."""
        job = Job(case_id=compliance_case.id, job_type=JobType.EXTRACT_ENTITIES)
        db_session.add(job)
        await db_session.flush()
        job_id = job.id

        error_msg = "Entity extraction timeout"
        job.mark_failed(error_msg)
        await db_session.flush()

        retrieved = await db_session.get(Job, job_id)
        assert retrieved.status == JobStatus.FAILED
        assert retrieved.error_message == error_msg
        assert retrieved.completed_at is not None

    async def test_multiple_jobs_for_same_case(
        self, db_session: AsyncSession, compliance_case: ComplianceCase
    ):
        """Test creating multiple jobs for the same case."""
        job1 = Job(case_id=compliance_case.id, job_type=JobType.EXTRACT_TEXT)
        job2 = Job(case_id=compliance_case.id, job_type=JobType.GENERATE_EMBEDDINGS)
        job3 = Job(case_id=compliance_case.id, job_type=JobType.RISK_ASSESSMENT)

        db_session.add_all([job1, job2, job3])
        await db_session.flush()

        # Verify all jobs exist
        assert job1.id is not None
        assert job2.id is not None
        assert job3.id is not None

        # Retrieve and verify
        retrieved_job1 = await db_session.get(Job, job1.id)
        retrieved_job2 = await db_session.get(Job, job2.id)
        retrieved_job3 = await db_session.get(Job, job3.id)

        assert retrieved_job1.case_id == compliance_case.id
        assert retrieved_job2.case_id == compliance_case.id
        assert retrieved_job3.case_id == compliance_case.id


@pytest.mark.integration
class TestJobRepository:
    """Tests for JobRepository persistence operations."""

    async def test_repository_create_job(
        self, db_session: AsyncSession, compliance_case: ComplianceCase
    ):
        """Test creating a job via repository."""
        repo = JobRepository()
        job = Job(case_id=compliance_case.id, job_type=JobType.EXTRACT_TEXT)

        created = await repo.create(db_session, job)
        await db_session.flush()

        assert created.id is not None
        assert created.case_id == compliance_case.id

    async def test_repository_read_job(
        self, db_session: AsyncSession, compliance_case: ComplianceCase
    ):
        """Test reading a job via repository."""
        repo = JobRepository()
        job = Job(case_id=compliance_case.id, job_type=JobType.EXTRACT_TEXT)
        db_session.add(job)
        await db_session.flush()

        retrieved = await repo.read(db_session, job.id)
        assert retrieved is not None
        assert retrieved.id == job.id
        assert retrieved.job_type == JobType.EXTRACT_TEXT

    async def test_repository_update_job_status(
        self, db_session: AsyncSession, compliance_case: ComplianceCase
    ):
        """Test updating a job via repository."""
        repo = JobRepository()
        job = Job(case_id=compliance_case.id, job_type=JobType.EXTRACT_TEXT)
        db_session.add(job)
        await db_session.flush()

        updated = await repo.update(db_session, job.id, {"status": JobStatus.PROCESSING.value})
        assert updated is not None
        assert updated.status == JobStatus.PROCESSING

    async def test_repository_delete_job(
        self, db_session: AsyncSession, compliance_case: ComplianceCase
    ):
        """Test deleting a job via repository."""
        repo = JobRepository()
        job = Job(case_id=compliance_case.id, job_type=JobType.EXTRACT_TEXT)
        db_session.add(job)
        await db_session.flush()
        job_id = job.id

        result = await repo.delete(db_session, job_id)
        assert result is True

        retrieved = await repo.read(db_session, job_id)
        assert retrieved is None

    async def test_repository_find_by_case(
        self, db_session: AsyncSession, compliance_case: ComplianceCase
    ):
        """Test finding jobs by case ID."""
        repo = JobRepository()
        job1 = Job(case_id=compliance_case.id, job_type=JobType.EXTRACT_TEXT)
        job2 = Job(case_id=compliance_case.id, job_type=JobType.GENERATE_EMBEDDINGS)
        db_session.add_all([job1, job2])
        await db_session.flush()

        found = await repo.find_by_case(db_session, compliance_case.id)
        assert len(found) >= 2
        assert all(job.case_id == compliance_case.id for job in found)

    async def test_repository_find_pending_jobs(
        self, db_session: AsyncSession, compliance_case: ComplianceCase
    ):
        """Test finding pending jobs."""
        repo = JobRepository()
        pending_job = Job(case_id=compliance_case.id, job_type=JobType.EXTRACT_TEXT)
        processing_job = Job(case_id=compliance_case.id, job_type=JobType.GENERATE_EMBEDDINGS)
        processing_job.status = JobStatus.PROCESSING

        db_session.add_all([pending_job, processing_job])
        await db_session.flush()

        pending = await repo.find_pending_jobs(db_session)
        pending_ids = [j.id for j in pending]
        assert pending_job.id in pending_ids
        assert processing_job.id not in pending_ids

    async def test_repository_list_by_filter_case_id(
        self, db_session: AsyncSession, compliance_case: ComplianceCase
    ):
        """Test filtering jobs by case_id."""
        repo = JobRepository()
        job = Job(case_id=compliance_case.id, job_type=JobType.EXTRACT_TEXT)
        db_session.add(job)
        await db_session.flush()

        results = await repo.list_by_filter(db_session, case_id=compliance_case.id)
        assert any(j.id == job.id for j in results)
        assert all(j.case_id == compliance_case.id for j in results)

    async def test_repository_list_by_filter_status(
        self, db_session: AsyncSession, compliance_case: ComplianceCase
    ):
        """Test filtering jobs by status."""
        repo = JobRepository()
        pending_job = Job(case_id=compliance_case.id, job_type=JobType.EXTRACT_TEXT)
        processing_job = Job(
            case_id=compliance_case.id,
            job_type=JobType.GENERATE_EMBEDDINGS,
            status=JobStatus.PROCESSING,
        )
        db_session.add_all([pending_job, processing_job])
        await db_session.flush()

        pending_results = await repo.list_by_filter(db_session, status=JobStatus.PENDING)
        processing_results = await repo.list_by_filter(db_session, status=JobStatus.PROCESSING)

        assert any(j.id == pending_job.id for j in pending_results)
        assert any(j.id == processing_job.id for j in processing_results)

    async def test_repository_list_by_filter_job_type(
        self, db_session: AsyncSession, compliance_case: ComplianceCase
    ):
        """Test filtering jobs by job_type."""
        repo = JobRepository()
        extract_job = Job(case_id=compliance_case.id, job_type=JobType.EXTRACT_TEXT)
        embedding_job = Job(case_id=compliance_case.id, job_type=JobType.GENERATE_EMBEDDINGS)
        db_session.add_all([extract_job, embedding_job])
        await db_session.flush()

        extract_results = await repo.list_by_filter(db_session, job_type=JobType.EXTRACT_TEXT)
        assert any(j.id == extract_job.id for j in extract_results)

    async def test_repository_protected_fields_cannot_be_updated(
        self, db_session: AsyncSession, compliance_case: ComplianceCase
    ):
        """Test that protected fields cannot be updated via repository."""
        repo = JobRepository()
        job = Job(case_id=compliance_case.id, job_type=JobType.EXTRACT_TEXT)
        db_session.add(job)
        await db_session.flush()

        with pytest.raises(ValueError, match="Cannot update protected fields"):
            await repo.update(db_session, job.id, {"id": uuid4()})

        with pytest.raises(ValueError, match="Cannot update protected fields"):
            await repo.update(db_session, job.id, {"created_at": datetime.now(UTC)})

        with pytest.raises(ValueError, match="Cannot update protected fields"):
            await repo.update(db_session, job.id, {"updated_at": datetime.now(UTC)})

    async def test_repository_invalid_filter_fields_raise_error(
        self, db_session: AsyncSession, compliance_case: ComplianceCase
    ):
        """Test that invalid filter fields raise ValueError."""
        repo = JobRepository()
        job = Job(case_id=compliance_case.id, job_type=JobType.EXTRACT_TEXT)
        db_session.add(job)
        await db_session.flush()

        with pytest.raises(ValueError, match="Unknown filter fields"):
            await repo.list_by_filter(db_session, invalid_field="value")

        with pytest.raises(ValueError, match="Unknown filter fields"):
            await repo.list_by_filter(db_session, error_message="some error")


@pytest.mark.integration
class TestJobCascadeDelete:
    """Tests for cascade delete behavior."""

    async def test_deleting_case_cascades_to_jobs(
        self, db_session: AsyncSession, compliance_case: ComplianceCase
    ):
        """Test that deleting a compliance case deletes its jobs."""
        job = Job(case_id=compliance_case.id, job_type=JobType.EXTRACT_TEXT)
        db_session.add(job)
        await db_session.flush()
        job_id = job.id

        # Delete the case
        await db_session.delete(compliance_case)
        await db_session.flush()

        # Verify job was cascade-deleted
        retrieved = await db_session.get(Job, job_id)
        assert retrieved is None
