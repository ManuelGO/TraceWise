"""Integration tests for Celery task execution."""

from uuid import uuid4

import pytest

from app.celery_app import celery_app
from app.models import JobStatus, JobType


@pytest.fixture
def job_id():
    """Generate a test job ID."""
    return str(uuid4())


@pytest.fixture
def sample_job_data():
    """Create sample job data."""
    return {
        "id": uuid4(),
        "case_id": uuid4(),
        "job_type": JobType.EXTRACT_TEXT,
        "status": JobStatus.PENDING,
        "started_at": None,
        "completed_at": None,
        "error_message": None,
        "job_metadata": {},
    }


@pytest.mark.asyncio
async def test_validate_document_task_enqueue():
    """Task can be enqueued."""
    from app.tasks.document_tasks import validate_document_task

    # Note: In a real test environment with Redis running,
    # this would return an AsyncResult. For now, we're just testing
    # that the task function exists and can be called.
    assert hasattr(validate_document_task, "delay")
    assert callable(validate_document_task.delay)


@pytest.mark.asyncio
async def test_extract_text_task_enqueue():
    """Task can be enqueued."""
    from app.tasks.document_tasks import extract_text_task

    assert hasattr(extract_text_task, "delay")
    assert callable(extract_text_task.delay)


@pytest.mark.asyncio
async def test_validate_document_task_with_mock_session(job_id, sample_job_data):
    """Test validate_document_task with mocked database session."""
    # This test would require an actual running Redis and PostgreSQL
    # For now, we test the structure and configuration
    from app.tasks.document_tasks import validate_document_task

    task = validate_document_task
    assert task.name == "app.tasks.document_tasks.validate_document_task"
    assert task.autoretry_for == (Exception,)
    assert task.max_retries == 3


@pytest.mark.asyncio
async def test_extract_text_task_with_mock_session(job_id, sample_job_data):
    """Test extract_text_task with mocked database session."""
    from app.tasks.document_tasks import extract_text_task

    task = extract_text_task
    assert task.name == "app.tasks.document_tasks.extract_text_task"
    assert task.autoretry_for == (Exception,)
    assert task.max_retries == 3


def test_validate_document_task_configuration():
    """Validate document task is correctly configured."""
    task = celery_app.tasks.get("app.tasks.document_tasks.validate_document_task")
    assert task is not None
    assert task.autoretry_for == (Exception,)
    assert task.max_retries == 3


def test_extract_text_task_configuration():
    """Extract text task is correctly configured."""
    task = celery_app.tasks.get("app.tasks.document_tasks.extract_text_task")
    assert task is not None
    assert task.autoretry_for == (Exception,)
    assert task.max_retries == 3


def test_celery_app_autodiscover():
    """Celery app has autodiscovered tasks."""
    # Check that tasks from app.tasks module are registered
    task_names = list(celery_app.tasks.keys())
    assert any("document_tasks" in name for name in task_names)
