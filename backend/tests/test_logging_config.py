import json
import logging

from app.config import Settings
from app.context import reset_context, set_context_var
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

    def test_json_formatter_includes_context(self):
        """JSON formatter should include context variables when set."""
        reset_context()
        set_context_var("request_id", "req-123")
        set_context_var("case_id", "case-456")

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

        assert log_data["request_id"] == "req-123"
        assert log_data["case_id"] == "case-456"
        assert "user_id" not in log_data  # Not set, should not be in output

        reset_context()

    def test_json_formatter_excludes_empty_context(self):
        """JSON formatter should exclude empty context fields."""
        reset_context()

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

        # No context fields should be present
        assert "request_id" not in log_data
        assert "case_id" not in log_data
        assert "user_id" not in log_data
        assert "document_id" not in log_data
        assert "session_id" not in log_data

        # But basic fields should still exist
        assert "timestamp" in log_data
        assert "level" in log_data
        assert "logger" in log_data
        assert "message" in log_data

    def test_json_formatter_backward_compat(self):
        """JSON formatter should work without context (backward compatible)."""
        reset_context()
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="app.api",
            level=logging.INFO,
            pathname="api.py",
            lineno=10,
            msg="Request processed",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        log_data = json.loads(output)

        # Should produce valid JSON with core fields
        assert isinstance(log_data, dict)
        assert log_data["message"] == "Request processed"
        assert log_data["logger"] == "app.api"
        assert log_data["level"] == "INFO"

    def test_json_formatter_sanitizes_context_values(self):
        """JSON formatter should coerce context values to strings and truncate long ones."""
        reset_context()
        # Set context with non-string and very long values
        set_context_var("request_id", "req-123")
        set_context_var("case_id", {"nested": "dict"})  # Non-string
        set_context_var("document_id", "x" * 500)  # Very long string

        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        log_data = json.loads(output)

        # All values should be strings
        assert isinstance(log_data["request_id"], str)
        assert log_data["request_id"] == "req-123"
        assert isinstance(log_data["case_id"], str)
        assert "nested" in log_data["case_id"]  # Dict converted to string repr
        # Long value should be truncated to 256 chars
        assert len(log_data["document_id"]) == 256
        assert log_data["document_id"] == "x" * 256

        reset_context()


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
