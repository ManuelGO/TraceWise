"""Celery application initialization for async task processing."""

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "tracewise",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_BACKEND_URL,
)

# Load configuration from celery_config module
celery_app.config_from_object("app.celery_config")

# Auto-discover tasks from app.tasks module
celery_app.autodiscover_tasks(["app.tasks"])
