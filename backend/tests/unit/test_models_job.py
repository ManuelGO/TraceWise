"""Unit tests for Job domain model."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.models import Job, JobStatus, JobType


class TestJobModel:
    """Tests for Job model instantiation and basic properties."""

    def test_job_instantiation_with_all_fields(self):
        """Test creating a Job with all fields populated."""
        case_id = uuid4()
        metadata = {"key": "value", "nested": {"inner": "data"}}
        error_msg = "Test error"

        job = Job(
            case_id=case_id,
            job_type=JobType.EXTRACT_TEXT,
            status=JobStatus.FAILED,
            error_message=error_msg,
            job_metadata=metadata,
        )

        assert job.case_id == case_id
        assert job.job_type == JobType.EXTRACT_TEXT
        assert job.status == JobStatus.FAILED
        assert job.error_message == error_msg
        assert job.job_metadata == metadata

    def test_job_instantiation_with_minimal_fields(self):
        """Test creating a Job with only required fields."""
        case_id = uuid4()

        job = Job(
            case_id=case_id,
            job_type=JobType.GENERATE_EMBEDDINGS,
        )

        assert job.case_id == case_id
        assert job.job_type == JobType.GENERATE_EMBEDDINGS
        assert job.status == JobStatus.PENDING
        assert job.job_metadata is None or job.job_metadata == {}
        assert job.error_message is None
        assert job.started_at is None
        assert job.completed_at is None

    def test_job_has_uuid_primary_key(self):
        """Test that Job generates a UUID primary key."""
        case_id = uuid4()
        job = Job(case_id=case_id, job_type=JobType.EXTRACT_TEXT)

        assert job.id is None or isinstance(job.id, type(uuid4()))

    def test_job_default_status_is_pending(self):
        """Test that status defaults to pending."""
        case_id = uuid4()
        job = Job(case_id=case_id, job_type=JobType.EXTRACT_TEXT)

        assert job.status == JobStatus.PENDING

    def test_job_repr(self):
        """Test Job __repr__ method."""
        case_id = uuid4()
        job = Job(case_id=case_id, job_type=JobType.EXTRACT_TEXT)
        job.id = uuid4()

        repr_str = repr(job)
        assert "Job" in repr_str
        assert "job_type" in repr_str
        assert "status" in repr_str

    def test_job_metadata_nullable(self):
        """Test that metadata field is nullable."""
        case_id = uuid4()
        job = Job(case_id=case_id, job_type=JobType.EXTRACT_TEXT, job_metadata=None)

        assert job.job_metadata is None or job.job_metadata == {}

    def test_job_metadata_accepts_dict(self):
        """Test that metadata can store complex JSON structures."""
        case_id = uuid4()
        metadata = {
            "text_config": {"max_length": 1000},
            "tags": ["urgent", "compliance"],
            "nested": {"level1": {"level2": "value"}},
        }
        job = Job(case_id=case_id, job_type=JobType.EXTRACT_TEXT, job_metadata=metadata)

        assert job.job_metadata == metadata


class TestJobEnums:
    """Tests for Job enum validation."""

    def test_job_type_values(self):
        """Test all valid JobType enum values."""
        assert JobType.EXTRACT_TEXT.value == "extract_text"
        assert JobType.GENERATE_EMBEDDINGS.value == "generate_embeddings"
        assert JobType.EXTRACT_ENTITIES.value == "extract_entities"
        assert JobType.RISK_ASSESSMENT.value == "risk_assessment"
        assert JobType.GENERATE_REPORT.value == "generate_report"

    def test_job_status_values(self):
        """Test all valid JobStatus enum values."""
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.PROCESSING.value == "processing"
        assert JobStatus.COMPLETED.value == "completed"
        assert JobStatus.FAILED.value == "failed"

    def test_job_type_enum_members(self):
        """Test JobType has exactly 6 members."""
        assert len(list(JobType)) == 6

    def test_job_status_enum_members(self):
        """Test JobStatus has exactly 4 members."""
        assert len(list(JobStatus)) == 4


class TestJobStateTransitions:
    """Tests for Job state transition methods."""

    def test_mark_processing_from_pending(self):
        """Test successful transition from pending to processing."""
        case_id = uuid4()
        job = Job(case_id=case_id, job_type=JobType.EXTRACT_TEXT)

        assert job.status == JobStatus.PENDING
        assert job.started_at is None

        job.mark_processing()

        assert job.status == JobStatus.PROCESSING
        assert job.started_at is not None
        assert isinstance(job.started_at, datetime)

    def test_mark_processing_sets_started_at_utc(self):
        """Test that mark_processing sets started_at in UTC."""
        case_id = uuid4()
        job = Job(case_id=case_id, job_type=JobType.EXTRACT_TEXT)
        before = datetime.now(UTC)

        job.mark_processing()

        after = datetime.now(UTC)
        assert before <= job.started_at <= after
        assert job.started_at.tzinfo == UTC

    def test_mark_processing_raises_when_not_pending(self):
        """Test that mark_processing fails if status is not pending."""
        case_id = uuid4()
        job = Job(case_id=case_id, job_type=JobType.EXTRACT_TEXT, status=JobStatus.PROCESSING)

        with pytest.raises(ValueError, match="Cannot transition to processing"):
            job.mark_processing()

    def test_mark_processing_raises_when_completed(self):
        """Test that mark_processing fails if job is already completed."""
        case_id = uuid4()
        job = Job(case_id=case_id, job_type=JobType.EXTRACT_TEXT, status=JobStatus.COMPLETED)

        with pytest.raises(ValueError, match="Cannot transition to processing"):
            job.mark_processing()

    def test_mark_processing_raises_when_failed(self):
        """Test that mark_processing fails if job has failed."""
        case_id = uuid4()
        job = Job(case_id=case_id, job_type=JobType.EXTRACT_TEXT, status=JobStatus.FAILED)

        with pytest.raises(ValueError, match="Cannot transition to processing"):
            job.mark_processing()

    def test_mark_completed_from_processing(self):
        """Test successful transition from processing to completed."""
        case_id = uuid4()
        job = Job(case_id=case_id, job_type=JobType.EXTRACT_TEXT)
        job.mark_processing()

        assert job.status == JobStatus.PROCESSING
        assert job.completed_at is None

        job.mark_completed()

        assert job.status == JobStatus.COMPLETED
        assert job.completed_at is not None
        assert isinstance(job.completed_at, datetime)

    def test_mark_completed_sets_completed_at_utc(self):
        """Test that mark_completed sets completed_at in UTC."""
        case_id = uuid4()
        job = Job(case_id=case_id, job_type=JobType.EXTRACT_TEXT)
        job.mark_processing()
        before = datetime.now(UTC)

        job.mark_completed()

        after = datetime.now(UTC)
        assert before <= job.completed_at <= after
        assert job.completed_at.tzinfo == UTC

    def test_mark_completed_raises_when_not_processing(self):
        """Test that mark_completed fails if status is not processing."""
        case_id = uuid4()
        job = Job(case_id=case_id, job_type=JobType.EXTRACT_TEXT)

        with pytest.raises(ValueError, match="Cannot transition to completed"):
            job.mark_completed()

    def test_mark_completed_raises_when_failed(self):
        """Test that mark_completed fails if job has failed."""
        case_id = uuid4()
        job = Job(case_id=case_id, job_type=JobType.EXTRACT_TEXT, status=JobStatus.FAILED)

        with pytest.raises(ValueError, match="Cannot transition to completed"):
            job.mark_completed()

    def test_mark_failed_from_pending(self):
        """Test successful transition from pending to failed."""
        case_id = uuid4()
        job = Job(case_id=case_id, job_type=JobType.EXTRACT_TEXT)
        error_msg = "Test error occurred"

        assert job.status == JobStatus.PENDING
        assert job.error_message is None
        assert job.completed_at is None

        job.mark_failed(error_msg)

        assert job.status == JobStatus.FAILED
        assert job.error_message == error_msg
        assert job.completed_at is not None

    def test_mark_failed_from_processing(self):
        """Test successful transition from processing to failed."""
        case_id = uuid4()
        job = Job(case_id=case_id, job_type=JobType.EXTRACT_TEXT)
        job.mark_processing()
        error_msg = "Processing error"

        job.mark_failed(error_msg)

        assert job.status == JobStatus.FAILED
        assert job.error_message == error_msg
        assert job.completed_at is not None

    def test_mark_failed_sets_completed_at_utc(self):
        """Test that mark_failed sets completed_at in UTC."""
        case_id = uuid4()
        job = Job(case_id=case_id, job_type=JobType.EXTRACT_TEXT)
        before = datetime.now(UTC)

        job.mark_failed("Error message")

        after = datetime.now(UTC)
        assert before <= job.completed_at <= after
        assert job.completed_at.tzinfo == UTC

    def test_mark_failed_raises_when_already_completed(self):
        """Test that mark_failed fails if job is already completed."""
        case_id = uuid4()
        job = Job(case_id=case_id, job_type=JobType.EXTRACT_TEXT, status=JobStatus.COMPLETED)

        with pytest.raises(ValueError, match="Cannot transition to failed"):
            job.mark_failed("Error")

    def test_mark_failed_raises_when_already_failed(self):
        """Test that mark_failed fails if job has already failed."""
        case_id = uuid4()
        job = Job(case_id=case_id, job_type=JobType.EXTRACT_TEXT, status=JobStatus.FAILED)

        with pytest.raises(ValueError, match="Cannot transition to failed"):
            job.mark_failed("Another error")

    def test_full_state_machine_pending_to_processing_to_completed(self):
        """Test full lifecycle: pending -> processing -> completed."""
        case_id = uuid4()
        job = Job(case_id=case_id, job_type=JobType.EXTRACT_TEXT)

        assert job.status == JobStatus.PENDING
        assert job.started_at is None
        assert job.completed_at is None

        job.mark_processing()
        assert job.status == JobStatus.PROCESSING
        assert job.started_at is not None
        assert job.completed_at is None

        job.mark_completed()
        assert job.status == JobStatus.COMPLETED
        assert job.started_at is not None
        assert job.completed_at is not None
        assert job.completed_at >= job.started_at

    def test_full_state_machine_pending_to_processing_to_failed(self):
        """Test full lifecycle: pending -> processing -> failed."""
        case_id = uuid4()
        job = Job(case_id=case_id, job_type=JobType.EXTRACT_TEXT)
        error_msg = "Processing timeout"

        job.mark_processing()
        assert job.status == JobStatus.PROCESSING

        job.mark_failed(error_msg)
        assert job.status == JobStatus.FAILED
        assert job.error_message == error_msg
        assert job.completed_at >= job.started_at

    def test_full_state_machine_pending_to_failed(self):
        """Test full lifecycle: pending -> failed (without processing)."""
        case_id = uuid4()
        job = Job(case_id=case_id, job_type=JobType.EXTRACT_TEXT)
        error_msg = "Validation failed"

        job.mark_failed(error_msg)
        assert job.status == JobStatus.FAILED
        assert job.error_message == error_msg
        assert job.started_at is None  # Never transitioned to processing
        assert job.completed_at is not None
