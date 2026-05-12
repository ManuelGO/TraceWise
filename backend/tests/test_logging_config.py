import json
import logging

from app.config import Settings
from app.logging import JSONFormatter, configure_logging, get_logger


class TestLoggingConfiguration:
    """Test logging configuration."""

    def test_configure_logging_development(self):
        """Development logging should use standard format."""
        settings = Settings(
            ENVIRONMENT="development",
            LOG_LEVEL="INFO",
            DATABASE_URL="postgresql://user:pass@localhost:5432/db",
        )
        configure_logging(settings)
        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO

    def test_configure_logging_production(self):
        """Production logging should use JSON format."""
        settings = Settings(
            ENVIRONMENT="production",
            LOG_LEVEL="WARNING",
            DATABASE_URL="postgresql://user:pass@localhost:5432/db",
        )
        configure_logging(settings)
        root_logger = logging.getLogger()
        assert root_logger.level == logging.WARNING

    def test_configure_logging_respects_log_level(self):
        """Logging configuration should respect LOG_LEVEL setting."""
        for level_name, level_int in [
            ("DEBUG", logging.DEBUG),
            ("INFO", logging.INFO),
            ("WARNING", logging.WARNING),
            ("ERROR", logging.ERROR),
            ("CRITICAL", logging.CRITICAL),
        ]:
            settings = Settings(
                LOG_LEVEL=level_name,
                DATABASE_URL="postgresql://user:pass@localhost:5432/db",
            )
            configure_logging(settings)
            root_logger = logging.getLogger()
            assert root_logger.level == level_int


class TestJSONFormatter:
    """Test JSON log formatting."""

    def test_json_formatter_basic(self):
        """JSON formatter should produce valid JSON with basic fields."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        log_data = json.loads(output)

        assert log_data["logger"] == "test.module"
        assert log_data["level"] == "INFO"
        assert log_data["message"] == "Test message"
        assert "timestamp" in log_data

    def test_json_formatter_with_exception(self):
        """JSON formatter should include exception information."""
        import sys

        formatter = JSONFormatter()
        try:
            raise ValueError("Test error")
        except ValueError:
            exc_info = sys.exc_info()
            record = logging.LogRecord(
                name="test.module",
                level=logging.ERROR,
                pathname="test.py",
                lineno=42,
                msg="Error occurred",
                args=(),
                exc_info=exc_info,
            )
        output = formatter.format(record)
        log_data = json.loads(output)

        assert "exception" in log_data
        assert "ValueError: Test error" in log_data["exception"]

    def test_json_formatter_different_levels(self):
        """JSON formatter should handle different log levels."""
        formatter = JSONFormatter()
        for level_name, level_int in [
            ("DEBUG", logging.DEBUG),
            ("INFO", logging.INFO),
            ("WARNING", logging.WARNING),
            ("ERROR", logging.ERROR),
            ("CRITICAL", logging.CRITICAL),
        ]:
            record = logging.LogRecord(
                name="test",
                level=level_int,
                pathname="test.py",
                lineno=1,
                msg="Test",
                args=(),
                exc_info=None,
            )
            output = formatter.format(record)
            log_data = json.loads(output)
            assert log_data["level"] == level_name


class TestGetLogger:
    """Test get_logger function."""

    def test_get_logger_returns_logger(self):
        """get_logger should return a Logger."""
        logger = get_logger("test.module")
        assert isinstance(logger, logging.Logger)

    def test_get_logger_has_correct_name(self):
        """get_logger should create logger with correct name."""
        logger = get_logger("test.module.submodule")
        assert logger.name == "test.module.submodule"

    def test_get_logger_can_log(self):
        """get_logger should return functional logger."""
        logger = get_logger("test")
        # Should not raise
        logger.info("Test message")
        logger.warning("Test warning")
        logger.error("Test error")
