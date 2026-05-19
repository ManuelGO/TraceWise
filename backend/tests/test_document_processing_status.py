"""Tests for document processing status tracking and job listing endpoint."""

import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ComplianceCase, Document, Job
from app.models.enums import (
    CaseStatus,
    DocumentType,
    JobStatus,
    JobType,
    ProcessingStatus,
    RiskLevel,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION_TESTS"),
    reason="Integration tests require RUN_INTEGRATION_TESTS env var",
)


@pytest_asyncio.fixture
async def case_with_document(db_session: AsyncSession) -> tuple[ComplianceCase, Document]:
    """Create a test compliance case with a document."""
    case = ComplianceCase(
        title="Test Case for Document Processing Status",
        description="Testing document status transitions",
        status=CaseStatus.ACTIVE,
        risk_level=RiskLevel.MEDIUM,
    )
    db_session.add(case)
    await db_session.flush()

    document = Document(
        case_id=case.id,
        filename="test_document.pdf",
        document_type=DocumentType.CERTIFICATE,
        storage_path="s3://test/documents/test.pdf",
        processing_status=ProcessingStatus.UPLOADED,
        file_size=1024,
        mime_type="application/pdf",
    )
    db_session.add(document)
    await db_session.commit()

    return case, document


@pytest.mark.integration
class TestDocumentProcessingStatus:
    """Test suite for document processing status fields and transitions."""

    async def test_document_defaults_to_uploaded(self, db_session: AsyncSession):
        """New documents should default to UPLOADED status."""
        case = ComplianceCase(
            title="Default Status Test",
            description="",
            status=CaseStatus.ACTIVE,
            risk_level=RiskLevel.LOW,
        )
        db_session.add(case)
        await db_session.flush()

        document = Document(
            case_id=case.id,
            filename="test.pdf",
            document_type=DocumentType.INVOICE,
            storage_path="s3://bucket/test.pdf",
            file_size=512,
            mime_type="application/pdf",
        )
        db_session.add(document)
        await db_session.commit()

        assert document.processing_status == ProcessingStatus.UPLOADED
        assert document.processing_error is None

    async def test_document_status_transitions(self, db_session: AsyncSession, case_with_document):
        """Test valid document status transitions."""
        case, document = case_with_document

        # Transition: UPLOADED → EXTRACTING
        document.processing_status = ProcessingStatus.EXTRACTING
        await db_session.commit()
        await db_session.refresh(document)
        assert document.processing_status == ProcessingStatus.EXTRACTING

        # Transition: EXTRACTING → EXTRACTED
        document.processing_status = ProcessingStatus.EXTRACTED
        await db_session.commit()
        await db_session.refresh(document)
        assert document.processing_status == ProcessingStatus.EXTRACTED

    async def test_document_failed_status_with_error(
        self, db_session: AsyncSession, case_with_document
    ):
        """Test document FAILED status with error message."""
        case, document = case_with_document

        error_msg = "Failed to extract text: unsupported file format"
        document.processing_status = ProcessingStatus.FAILED
        document.processing_error = error_msg
        await db_session.commit()
        await db_session.refresh(document)

        assert document.processing_status == ProcessingStatus.FAILED
        assert document.processing_error == error_msg

    async def test_processing_error_nullable(self, db_session: AsyncSession, case_with_document):
        """Processing error should be NULL for successful documents."""
        case, document = case_with_document

        document.processing_status = ProcessingStatus.EXTRACTED
        document.processing_error = None
        await db_session.commit()
        await db_session.refresh(document)

        assert document.processing_status == ProcessingStatus.EXTRACTED
        assert document.processing_error is None

    async def test_validating_to_uploaded_transition(
        self, db_session: AsyncSession, case_with_document
    ):
        """Test validation success returns to UPLOADED."""
        case, document = case_with_document

        # Start validation
        document.processing_status = ProcessingStatus.VALIDATING
        await db_session.commit()
        await db_session.refresh(document)
        assert document.processing_status == ProcessingStatus.VALIDATING

        # Validation passes, return to UPLOADED
        document.processing_status = ProcessingStatus.UPLOADED
        await db_session.commit()
        await db_session.refresh(document)
        assert document.processing_status == ProcessingStatus.UPLOADED

    async def test_validating_to_failed_transition(
        self, db_session: AsyncSession, case_with_document
    ):
        """Test validation failure transitions to FAILED."""
        case, document = case_with_document

        # Start validation
        document.processing_status = ProcessingStatus.VALIDATING
        await db_session.commit()

        # Validation fails
        document.processing_status = ProcessingStatus.FAILED
        document.processing_error = "Invalid file: corrupted PDF"
        await db_session.commit()
        await db_session.refresh(document)

        assert document.processing_status == ProcessingStatus.FAILED
        assert document.processing_error == "Invalid file: corrupted PDF"


@pytest.mark.integration
class TestJobListing:
    """Test suite for GET /cases/{case_id}/jobs endpoint."""

    async def test_list_jobs_empty_case(self, db_session: AsyncSession, client):
        """List jobs for case with no jobs should return empty array."""
        case = ComplianceCase(
            title="Empty Case",
            description="",
            status=CaseStatus.ACTIVE,
            risk_level=RiskLevel.MEDIUM,
        )
        db_session.add(case)
        await db_session.commit()

        response = client.get(f"/cases/{case.id}/jobs")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["skip"] == 0
        assert data["limit"] == 20

    async def test_list_jobs_with_multiple_jobs(self, db_session: AsyncSession, client):
        """List jobs for case with multiple jobs."""
        case = ComplianceCase(
            title="Multi-Job Case",
            description="",
            status=CaseStatus.ACTIVE,
            risk_level=RiskLevel.HIGH,
        )
        db_session.add(case)
        await db_session.flush()

        # Create 5 jobs
        for i in range(5):
            job = Job(
                case_id=case.id,
                job_type=JobType.EXTRACT_TEXT,
                status=JobStatus.PENDING if i % 2 == 0 else JobStatus.COMPLETED,
            )
            db_session.add(job)
        await db_session.commit()

        response = client.get(f"/cases/{case.id}/jobs")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5
        assert data["total"] == 5

    async def test_list_jobs_pagination(self, db_session: AsyncSession, client):
        """Test pagination parameters in job listing."""
        case = ComplianceCase(
            title="Pagination Test Case",
            description="",
            status=CaseStatus.ACTIVE,
            risk_level=RiskLevel.LOW,
        )
        db_session.add(case)
        await db_session.flush()

        # Create 50 jobs
        for i in range(50):
            job = Job(
                case_id=case.id,
                job_type=JobType.EXTRACT_TEXT,
                status=JobStatus.PENDING,
            )
            db_session.add(job)
        await db_session.commit()

        # Test default pagination
        response = client.get(f"/cases/{case.id}/jobs")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 20  # default limit
        assert data["total"] == 50
        assert data["skip"] == 0
        assert data["limit"] == 20

        # Test with custom skip/limit
        response = client.get(f"/cases/{case.id}/jobs?skip=10&limit=15")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 15
        assert data["total"] == 50
        assert data["skip"] == 10
        assert data["limit"] == 15

    async def test_list_jobs_case_not_found(self, client):
        """List jobs for non-existent case should return 404."""
        fake_case_id = uuid4()
        response = client.get(f"/cases/{fake_case_id}/jobs")
        assert response.status_code == 404

    async def test_job_serialization(self, db_session: AsyncSession, client):
        """Job list should include all required fields."""
        case = ComplianceCase(
            title="Job Serialization Test",
            description="",
            status=CaseStatus.ACTIVE,
            risk_level=RiskLevel.MEDIUM,
        )
        db_session.add(case)
        await db_session.flush()

        job = Job(
            case_id=case.id,
            job_type=JobType.EXTRACT_TEXT,
            status=JobStatus.COMPLETED,
            error_message=None,
        )
        db_session.add(job)
        await db_session.commit()

        response = client.get(f"/cases/{case.id}/jobs")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

        job_data = data["items"][0]
        assert "id" in job_data
        assert "case_id" in job_data
        assert "job_type" in job_data
        assert "status" in job_data
        assert "created_at" in job_data
        assert "started_at" in job_data
        assert "completed_at" in job_data
        assert "error_message" in job_data

    async def test_job_with_error_message(self, db_session: AsyncSession, client):
        """Failed job should include error message."""
        case = ComplianceCase(
            title="Failed Job Test",
            description="",
            status=CaseStatus.ACTIVE,
            risk_level=RiskLevel.MEDIUM,
        )
        db_session.add(case)
        await db_session.flush()

        job = Job(
            case_id=case.id,
            job_type=JobType.EXTRACT_TEXT,
            status=JobStatus.FAILED,
            error_message="PDF extraction failed: timeout",
        )
        db_session.add(job)
        await db_session.commit()

        response = client.get(f"/cases/{case.id}/jobs")
        assert response.status_code == 200
        data = response.json()

        job_data = data["items"][0]
        assert job_data["status"] == "failed"
        assert job_data["error_message"] == "PDF extraction failed: timeout"


class TestProcessingStatusEnum:
    """Test suite for ProcessingStatus enum values."""

    def test_enum_values(self):
        """ProcessingStatus should have all required values."""
        assert ProcessingStatus.UPLOADED.value == "uploaded"
        assert ProcessingStatus.VALIDATING.value == "validating"
        assert ProcessingStatus.EXTRACTING.value == "extracting"
        assert ProcessingStatus.EXTRACTED.value == "extracted"
        assert ProcessingStatus.EMBEDDING.value == "embedding"
        assert ProcessingStatus.READY.value == "ready"
        assert ProcessingStatus.FAILED.value == "failed"

    def test_enum_count(self):
        """ProcessingStatus should have exactly 7 values."""
        assert len(ProcessingStatus) == 7
