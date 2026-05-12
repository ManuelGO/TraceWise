import json
import logging
import sys

from app.config import Settings
from app.context import CONTEXT_VAR_NAMES, get_context_var

# Maximum length for context values to prevent log injection and resource exhaustion
_MAX_CONTEXT_LENGTH = 256


class JSONFormatter(logging.Formatter):
    """Format logs as JSON for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add context variables if they are set (sanitized to prevent log injection)
        for context_field in CONTEXT_VAR_NAMES:
            context_value = get_context_var(context_field)
            if context_value is not None:
                # Coerce to string and truncate to prevent log injection and resource exhaustion
                log_data[context_field] = str(context_value)[:_MAX_CONTEXT_LENGTH]

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def configure_logging(settings: Settings) -> None:
    """Configure application logging based on environment."""
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.LOG_LEVEL)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(settings.LOG_LEVEL)

    if settings.ENVIRONMENT == "production":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name."""
    return logging.getLogger(name)
