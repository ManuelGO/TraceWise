"""File validation service for document uploads."""

import logging
from pathlib import Path

import magic

from app.exceptions import (
    FileExtensionMismatchError,
    FileSizeTooLargeError,
    MimeTypeNotAllowedError,
)

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 52_428_800  # 50MB in bytes

SUPPORTED_MIME_TYPES = [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # DOCX
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # XLSX
    "text/csv",
    "text/plain",
]

EXTENSION_MIME_MAP = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
    ".txt": "text/plain",
}


def validate_file_size(file_size: int, max_bytes: int = MAX_FILE_SIZE) -> None:
    """Validate that file size does not exceed maximum.

    Args:
        file_size: File size in bytes
        max_bytes: Maximum allowed size (default 50MB)

    Raises:
        FileSizeTooLargeError: If file exceeds maximum size
    """
    if file_size > max_bytes:
        raise FileSizeTooLargeError(actual_size=file_size, max_size=max_bytes)


def validate_mime_type(file_bytes: bytes) -> str:
    """Detect and validate MIME type via magic bytes.

    Uses python-magic to inspect file content directly, ignoring client-supplied
    Content-Type headers. This is security-critical to prevent file spoofing.

    Args:
        file_bytes: Raw file content bytes

    Returns:
        Detected MIME type (trusted, from magic bytes)

    Raises:
        MimeTypeNotAllowedError: If detected type not in supported list
    """
    mime = magic.Magic(mime=True)
    detected_mime = mime.from_buffer(file_bytes)

    if detected_mime not in SUPPORTED_MIME_TYPES:
        raise MimeTypeNotAllowedError(
            detected_type=detected_mime, allowed_types=SUPPORTED_MIME_TYPES
        )

    return detected_mime


def validate_extension(filename: str, detected_mime: str) -> None:
    """Validate that file extension matches detected MIME type.

    Args:
        filename: Original filename (with extension)
        detected_mime: MIME type detected from magic bytes

    Raises:
        FileExtensionMismatchError: If extension does not match MIME type
    """
    extension = Path(filename).suffix.lower()

    # Files without extension are allowed (MIME type alone is authoritative)
    if not extension:
        return

    # Check if extension maps to the detected MIME type
    expected_mime = EXTENSION_MIME_MAP.get(extension)
    if expected_mime is None:
        # Extension not in our map; allow it if MIME type is supported
        # (the file could legitimately have an unsupported extension)
        return

    # Extension exists in map; verify it matches detected MIME
    if expected_mime != detected_mime:
        raise FileExtensionMismatchError(
            expected_mime=detected_mime, found_extension=extension, filename=filename
        )
