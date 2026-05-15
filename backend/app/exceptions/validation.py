"""Custom exceptions for file validation logic."""


class FileSizeTooLargeError(ValueError):
    """Raised when file size exceeds maximum allowed limit."""

    def __init__(self, actual_size: int, max_size: int = 52428800) -> None:
        self.actual_size = actual_size
        self.max_size = max_size
        super().__init__(f"File size {actual_size} bytes exceeds maximum {max_size} bytes")


class MimeTypeNotAllowedError(ValueError):
    """Raised when detected MIME type is not in the allowed list."""

    def __init__(self, detected_type: str, allowed_types: list[str]) -> None:
        self.detected_type = detected_type
        self.allowed_types = allowed_types
        super().__init__(
            f"File type {detected_type} is not allowed. "
            f"Allowed types: {', '.join(allowed_types)}"
        )


class FileExtensionMismatchError(ValueError):
    """Raised when file extension does not match detected MIME type."""

    def __init__(self, expected_mime: str, found_extension: str, filename: str) -> None:
        self.expected_mime = expected_mime
        self.found_extension = found_extension
        self.filename = filename
        super().__init__(
            f"Extension {found_extension} does not match detected MIME type {expected_mime} "
            f"(file: {filename})"
        )
