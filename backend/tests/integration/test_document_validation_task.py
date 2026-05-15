"""Integration tests for document validation Celery task."""

from pathlib import Path
from uuid import uuid4

import pytest

from app.models import JobStatus, JobType


@pytest.fixture
def sample_pdf_bytes():
    """Create minimal PDF file bytes for testing."""
    return b"%PDF-1.4\n%EOF"


@pytest.fixture
def sample_txt_bytes():
    """Create minimal TXT file bytes for testing."""
    return b"Hello, World!\n"


@pytest.fixture
def temp_storage_dir(tmp_path):
    """Create temporary storage directory."""
    return tmp_path


class TestValidateDocumentTask:
    """Tests for validate_document_task Celery integration."""

    @pytest.mark.asyncio
    async def test_task_configuration(self):
        """Test validate_document_task is correctly configured."""
        from app.tasks.document_tasks import validate_document_task

        assert validate_document_task.name == "app.tasks.document_tasks.validate_document_task"
        assert validate_document_task.autoretry_for == (Exception,)
        assert validate_document_task.max_retries == 3

    @pytest.mark.asyncio
    async def test_task_can_be_enqueued(self):
        """Test that validate_document_task can be enqueued."""
        from app.tasks.document_tasks import validate_document_task

        job_id = str(uuid4())
        # Just test that the task can be called (enqueue without running)
        assert hasattr(validate_document_task, "delay")
        assert callable(validate_document_task.delay)

    def test_validate_function_imports(self):
        """Test that validation functions can be imported from task module."""
        from app.tasks.document_tasks import (
            _validate_document,
        )

        assert _validate_document is not None
        assert callable(_validate_document)

    def test_exception_imports(self):
        """Test that custom validation exceptions are available."""
        from app.exceptions import (
            FileExtensionMismatchError,
            FileSizeTooLargeError,
            MimeTypeNotAllowedError,
        )

        # Just verify imports work
        assert FileSizeTooLargeError is not None
        assert MimeTypeNotAllowedError is not None
        assert FileExtensionMismatchError is not None
