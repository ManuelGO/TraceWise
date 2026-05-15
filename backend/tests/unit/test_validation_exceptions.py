"""Unit tests for custom validation exceptions."""

from app.exceptions import (
    FileExtensionMismatchError,
    FileSizeTooLargeError,
    MimeTypeNotAllowedError,
)


class TestFileSizeTooLargeError:
    """Tests for FileSizeTooLargeError."""

    def test_creation_with_default_max_size(self) -> None:
        """Test exception creation with default max size (50MB)."""
        exc = FileSizeTooLargeError(actual_size=60_000_000)
        assert exc.actual_size == 60_000_000
        assert exc.max_size == 52_428_800
        assert "60000000" in str(exc)
        assert "52428800" in str(exc)

    def test_creation_with_custom_max_size(self) -> None:
        """Test exception creation with custom max size."""
        exc = FileSizeTooLargeError(actual_size=10_000_000, max_size=5_000_000)
        assert exc.actual_size == 10_000_000
        assert exc.max_size == 5_000_000
        assert "10000000" in str(exc)
        assert "5000000" in str(exc)

    def test_error_message_format(self) -> None:
        """Test that error message includes both sizes."""
        exc = FileSizeTooLargeError(actual_size=100, max_size=50)
        assert str(exc) == "File size 100 bytes exceeds maximum 50 bytes"

    def test_inherits_from_valueerror(self) -> None:
        """Test that exception inherits from ValueError."""
        exc = FileSizeTooLargeError(actual_size=100, max_size=50)
        assert isinstance(exc, ValueError)


class TestMimeTypeNotAllowedError:
    """Tests for MimeTypeNotAllowedError."""

    def test_creation_single_allowed_type(self) -> None:
        """Test exception creation with single allowed type."""
        exc = MimeTypeNotAllowedError("application/exe", ["application/pdf"])
        assert exc.detected_type == "application/exe"
        assert exc.allowed_types == ["application/pdf"]
        assert "application/exe" in str(exc)
        assert "application/pdf" in str(exc)

    def test_creation_multiple_allowed_types(self) -> None:
        """Test exception creation with multiple allowed types."""
        allowed = ["application/pdf", "text/csv", "text/plain"]
        exc = MimeTypeNotAllowedError("image/png", allowed)
        assert exc.detected_type == "image/png"
        assert exc.allowed_types == allowed
        assert "image/png" in str(exc)
        for mime_type in allowed:
            assert mime_type in str(exc)

    def test_error_message_format(self) -> None:
        """Test that error message includes detected and allowed types."""
        allowed = ["application/pdf", "text/csv"]
        exc = MimeTypeNotAllowedError("application/exe", allowed)
        msg = str(exc)
        assert "application/exe" in msg
        assert "application/pdf" in msg
        assert "text/csv" in msg
        assert "Allowed types:" in msg

    def test_inherits_from_valueerror(self) -> None:
        """Test that exception inherits from ValueError."""
        exc = MimeTypeNotAllowedError("application/exe", ["application/pdf"])
        assert isinstance(exc, ValueError)


class TestFileExtensionMismatchError:
    """Tests for FileExtensionMismatchError."""

    def test_creation_with_details(self) -> None:
        """Test exception creation with all details."""
        exc = FileExtensionMismatchError(
            expected_mime="application/pdf", found_extension=".txt", filename="test.txt"
        )
        assert exc.expected_mime == "application/pdf"
        assert exc.found_extension == ".txt"
        assert exc.filename == "test.txt"

    def test_error_message_includes_all_details(self) -> None:
        """Test that error message includes MIME, extension, and filename."""
        exc = FileExtensionMismatchError(
            expected_mime="application/pdf", found_extension=".txt", filename="test.txt"
        )
        msg = str(exc)
        assert "application/pdf" in msg
        assert ".txt" in msg
        assert "test.txt" in msg

    def test_error_message_format(self) -> None:
        """Test error message format is descriptive."""
        exc = FileExtensionMismatchError(
            expected_mime="text/csv", found_extension=".docx", filename="data.docx"
        )
        msg = str(exc)
        assert ".docx" in msg
        assert "text/csv" in msg
        assert "data.docx" in msg
        assert "does not match" in msg

    def test_inherits_from_valueerror(self) -> None:
        """Test that exception inherits from ValueError."""
        exc = FileExtensionMismatchError(
            expected_mime="application/pdf", found_extension=".txt", filename="test.txt"
        )
        assert isinstance(exc, ValueError)
