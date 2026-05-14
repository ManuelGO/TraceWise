"""Unit tests for Celery configuration and initialization."""

from app.celery_app import celery_app
from app.config import get_settings
from app.tasks.document_tasks import extract_text_task, validate_document_task  # noqa: F401


def test_celery_app_initialized():
    """Celery app initializes without errors."""
    assert celery_app is not None
    assert celery_app.main == "tracewise"


def test_celery_broker_url_configured():
    """Broker URL configured correctly."""
    settings = get_settings()
    assert celery_app.conf.broker_url == settings.CELERY_BROKER_URL
    assert "/0" in celery_app.conf.broker_url  # Broker is on Redis DB 0


def test_celery_backend_url_configured():
    """Backend URL configured correctly."""
    settings = get_settings()
    assert celery_app.conf.result_backend == settings.CELERY_BACKEND_URL
    assert "/1" in celery_app.conf.result_backend  # Backend is on Redis DB 1


def test_celery_serializer_is_json():
    """Serializer configured as JSON."""
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.result_serializer == "json"
    assert celery_app.conf.accept_content == ["json"]


def test_celery_timezone_is_utc():
    """Timezone configured as UTC."""
    assert celery_app.conf.timezone == "UTC"
    assert celery_app.conf.enable_utc is True


def test_celery_task_tracking_enabled():
    """Task tracking is enabled."""
    assert celery_app.conf.task_track_started is True


def test_celery_task_timeout_configured():
    """Task timeout configured to 30 minutes."""
    assert celery_app.conf.task_time_limit == 30 * 60
    assert celery_app.conf.task_soft_time_limit == 29 * 60


def test_task_registration():
    """All tasks registered with Celery."""
    assert "app.tasks.document_tasks.validate_document_task" in celery_app.tasks
    assert "app.tasks.document_tasks.extract_text_task" in celery_app.tasks


def test_task_routes_configured():
    """Task routes configured in celery config."""
    assert celery_app.conf.task_routes is not None
    assert "app.tasks.document_tasks.validate_document_task" in celery_app.conf.task_routes
    assert "app.tasks.document_tasks.extract_text_task" in celery_app.conf.task_routes
