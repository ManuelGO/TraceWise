"""Unit tests for file validation service."""

import pytest

from app.exceptions import (
    FileExtensionMismatchError,
    FileSizeTooLargeError,
    MimeTypeNotAllowedError,
)
from app.services.file_validator import (
    MAX_FILE_SIZE,
    validate_extension,
    validate_file_size,
    validate_mime_type,
)


class TestValidateFileSize:
    """Tests for validate_file_size function."""

    def test_valid_file_under_limit(self) -> None:
        """Test that files under limit pass validation."""
        validate_file_size(1_000_000)  # 1MB
        validate_file_size(10_000_000)  # 10MB
        validate_file_size(49_000_000)  # 49MB

    def test_valid_file_at_limit(self) -> None:
        """Test that files exactly at 50MB pass."""
        validate_file_size(MAX_FILE_SIZE)

    def test_empty_file(self) -> None:
        """Test that empty files (0 bytes) pass."""
        validate_file_size(0)

    def test_file_over_limit(self) -> None:
        """Test that files over limit raise error."""
        with pytest.raises(FileSizeTooLargeError) as exc_info:
            validate_file_size(60_000_000)  # 60MB
        assert exc_info.value.actual_size == 60_000_000
        assert exc_info.value.max_size == MAX_FILE_SIZE

    def test_file_slightly_over_limit(self) -> None:
        """Test that files even 1 byte over limit raise error."""
        with pytest.raises(FileSizeTooLargeError):
            validate_file_size(MAX_FILE_SIZE + 1)

    def test_custom_max_size(self) -> None:
        """Test validation with custom max size."""
        custom_max = 1_000_000  # 1MB
        validate_file_size(500_000, max_bytes=custom_max)

        with pytest.raises(FileSizeTooLargeError):
            validate_file_size(1_500_000, max_bytes=custom_max)


class TestValidateMimeType:
    """Tests for validate_mime_type function."""

    # Common file signatures (magic bytes)
    PDF_BYTES = b"%PDF-1.4\n"
    TXT_BYTES = b"Hello, world!"
    CSV_BYTES = b"name,age,city\nJohn,30,NYC\n"

    def test_pdf_detection(self) -> None:
        """Test PDF MIME type detection."""
        result = validate_mime_type(self.PDF_BYTES)
        assert result == "application/pdf"

    def test_txt_detection(self) -> None:
        """Test plain text MIME type detection."""
        result = validate_mime_type(self.TXT_BYTES)
        assert result == "text/plain"

    def test_csv_detection(self) -> None:
        """Test CSV MIME type detection."""
        result = validate_mime_type(self.CSV_BYTES)
        # CSV might be detected as text/plain or text/csv depending on content
        assert result in ["text/csv", "text/plain"]

    def test_unsupported_format_raises_error(self) -> None:
        """Test that unsupported MIME types raise error."""
        # Zip file signature (unsupported)
        zip_bytes = b"PK\x03\x04"
        with pytest.raises(MimeTypeNotAllowedError) as exc_info:
            validate_mime_type(zip_bytes)
        # ZIP is detected as application/octet-stream (unsupported)
        assert (
            "octet-stream" in str(exc_info.value).lower()
            or "not allowed" in str(exc_info.value).lower()
        )

    def test_error_includes_allowed_types(self) -> None:
        """Test that error message includes list of allowed types."""
        # EXE file signature (unsupported)
        exe_bytes = b"MZ\x90\x00"
        with pytest.raises(MimeTypeNotAllowedError) as exc_info:
            validate_mime_type(exe_bytes)
        error_msg = str(exc_info.value)
        # Should mention error and allowed types
        assert "not allowed" in error_msg.lower() and (
            "application/pdf" in error_msg or "text/plain" in error_msg
        )


class TestValidateExtension:
    """Tests for validate_extension function."""

    PDF_MIME = "application/pdf"
    TXT_MIME = "text/plain"
    CSV_MIME = "text/csv"

    def test_matching_extension_and_mime_pdf(self) -> None:
        """Test that matching PDF extension and MIME passes."""
        validate_extension("document.pdf", self.PDF_MIME)

    def test_matching_extension_and_mime_txt(self) -> None:
        """Test that matching TXT extension and MIME passes."""
        validate_extension("readme.txt", self.TXT_MIME)

    def test_matching_extension_and_mime_csv(self) -> None:
        """Test that matching CSV extension and MIME passes."""
        validate_extension("data.csv", self.CSV_MIME)

    def test_case_insensitive_extension(self) -> None:
        """Test that extension matching is case-insensitive."""
        validate_extension("document.PDF", self.PDF_MIME)
        validate_extension("readme.TXT", self.TXT_MIME)
        validate_extension("Document.Pdf", self.PDF_MIME)

    def test_mismatched_extension_and_mime(self) -> None:
        """Test that mismatched extension and MIME raises error."""
        with pytest.raises(FileExtensionMismatchError) as exc_info:
            validate_extension("document.pdf", self.TXT_MIME)
        assert exc_info.value.expected_mime == self.TXT_MIME
        assert exc_info.value.found_extension == ".pdf"

    def test_mismatched_txt_as_pdf(self) -> None:
        """Test TXT file named as PDF raises error."""
        with pytest.raises(FileExtensionMismatchError):
            validate_extension("readme.txt", self.PDF_MIME)

    def test_no_extension_allowed(self) -> None:
        """Test that files with no extension are allowed."""
        # Files without extension should pass (MIME type is authoritative)
        validate_extension("document", self.PDF_MIME)
        validate_extension("data", self.CSV_MIME)
        validate_extension("readme", self.TXT_MIME)

    def test_unknown_extension_with_supported_mime(self) -> None:
        """Test that unknown extensions with supported MIME pass."""
        # Extension .xyz is not in our map, so it's allowed
        validate_extension("file.xyz", self.PDF_MIME)

    def test_error_message_includes_details(self) -> None:
        """Test that error message includes all relevant details."""
        with pytest.raises(FileExtensionMismatchError) as exc_info:
            validate_extension("file.pdf", self.TXT_MIME)
        error_msg = str(exc_info.value)
        assert "file.pdf" in error_msg
        assert ".pdf" in error_msg
        assert self.TXT_MIME in error_msg


class TestIntegrationValidation:
    """Integration tests for validation pipeline."""

    PDF_BYTES = b"%PDF-1.4\n"

    def test_valid_pdf_workflow(self) -> None:
        """Test complete validation pipeline for valid PDF."""
        # Size check
        validate_file_size(len(self.PDF_BYTES))

        # MIME detection
        detected_mime = validate_mime_type(self.PDF_BYTES)
        assert detected_mime == "application/pdf"

        # Extension validation
        validate_extension("document.pdf", detected_mime)

    def test_oversized_file_fails_immediately(self) -> None:
        """Test that oversized file fails before MIME detection."""
        oversized_bytes = b"\x00" * (52_428_800 + 1)
        with pytest.raises(FileSizeTooLargeError):
            validate_file_size(len(oversized_bytes))
        # MIME detection should not be called

    def test_unsupported_file_type_fails(self) -> None:
        """Test that unsupported file types fail during MIME detection."""
        # Zip file (detected as octet-stream, which is unsupported)
        zip_bytes = b"PK\x03\x04"
        with pytest.raises(MimeTypeNotAllowedError):
            validate_mime_type(zip_bytes)

    def test_mismatched_extension_fails(self) -> None:
        """Test that mismatched extension fails."""
        detected_mime = validate_mime_type(self.PDF_BYTES)
        with pytest.raises(FileExtensionMismatchError):
            validate_extension("document.txt", detected_mime)
