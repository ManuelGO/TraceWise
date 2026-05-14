"""Celery configuration for async task processing."""

# Task configuration
task_serializer = "json"
accept_content = ["json"]
result_serializer = "json"
timezone = "UTC"
enable_utc = True

# Task tracking and monitoring
task_track_started = True
task_acks_late = True
worker_prefetch_multiplier = 1

# Timeouts
task_time_limit = 30 * 60  # 30 minutes
task_soft_time_limit = 29 * 60  # 29 minutes (soft limit before hard kill)

# Task routing (will be expanded in Task 28)
task_routes = {
    "app.tasks.document_tasks.validate_document_task": {"queue": "default"},
    "app.tasks.document_tasks.extract_text_task": {"queue": "default"},
}

# Result backend configuration
result_expires = 3600  # Results expire after 1 hour

# Worker configuration
worker_log_format = "[%(asctime)s: %(levelname)s/%(processName)s] %(message)s"
worker_task_log_format = (
    "[%(asctime)s: %(levelname)s/%(processName)s] " "[%(task_name)s(%(task_id)s)] %(message)s"
)
