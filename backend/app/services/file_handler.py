"""File handling utilities for document uploads."""

import logging
import os
from pathlib import Path
from uuid import UUID

logger = logging.getLogger(__name__)


class FileSizeTooLargeError(ValueError):
    """Raised when file size exceeds maximum limit."""

    pass


class MimeTypeNotAllowedError(ValueError):
    """Raised when MIME type is not in allowed list."""

    pass


# MIME type to document type mapping
MIME_TYPE_DOCUMENT_TYPE_MAP = {
    "application/pdf": "other",
    "image/jpeg": "other",
    "image/png": "other",
    "image/gif": "other",
    "image/webp": "other",
    "application/vnd.ms-excel": "invoice",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "invoice",
    "application/msword": "other",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "other",
    "text/plain": "other",
    "text/csv": "invoice",
    "application/json": "geojson",
}

# File extension to document type mapping
EXTENSION_DOCUMENT_TYPE_MAP = {
    ".pdf": "other",
    ".jpg": "other",
    ".jpeg": "other",
    ".png": "other",
    ".gif": "other",
    ".webp": "other",
    ".xls": "invoice",
    ".xlsx": "invoice",
    ".doc": "other",
    ".docx": "other",
    ".txt": "other",
    ".csv": "invoice",
    ".json": "geojson",
    ".geojson": "geojson",
}


def validate_file_size(file_size: int, max_bytes: int) -> None:
    """Validate file size does not exceed maximum.

    Args:
        file_size: File size in bytes
        max_bytes: Maximum allowed size in bytes

    Raises:
        FileSizeTooLargeError: If file size exceeds maximum
    """
    if file_size > max_bytes:
        raise FileSizeTooLargeError(
            f"File size {file_size} bytes exceeds maximum {max_bytes} bytes"
        )


def validate_mime_type(mime_type: str, allowed_types: list[str]) -> None:
    """Validate MIME type is in whitelist.

    Args:
        mime_type: MIME type to validate
        allowed_types: List of allowed MIME types

    Raises:
        MimeTypeNotAllowedError: If MIME type not in whitelist
    """
    if mime_type not in allowed_types:
        raise MimeTypeNotAllowedError(f"MIME type {mime_type!r} is not allowed")


def validate_mime_type_by_magic_bytes(
    file_content: bytes,
    allowed_types: list[str],
    filename: str,
) -> str:
    """Detect true MIME type via magic bytes; reject if not allowed.

    Detects the actual MIME type of the file content using magic bytes
    (file signature inspection), not the client-supplied Content-Type header.
    Falls back to extension-based detection if magic bytes are inconclusive.

    Args:
        file_content: Raw file bytes
        allowed_types: Whitelist of allowed MIME types
        filename: Original filename (for extension fallback)

    Returns:
        Detected MIME type (safe to store in database)

    Raises:
        MimeTypeNotAllowedError: If detected type not in allowed list
    """
    try:
        import filetype
    except ImportError:
        # Graceful fallback if filetype not installed (for now)
        logger.warning("filetype library not installed; using extension-based detection")
        filetype = None

    actual_mime = None

    # Try magic-byte detection if filetype library available
    if filetype:
        detected = filetype.guess(file_content[:512])
        actual_mime = detected.mime if detected else None

    # Fallback: detect by extension
    if not actual_mime:
        ext = Path(filename).suffix.lower()
        ext_map = {
            ".pdf": "application/pdf",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".csv": "text/csv",
            ".txt": "text/plain",
            ".geojson": "application/json",
            ".json": "application/json",
            ".xls": "application/vnd.ms-excel",
            ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ".doc": "application/msword",
            ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        }
        actual_mime = ext_map.get(ext)

    # Final fallback
    if not actual_mime:
        actual_mime = "application/octet-stream"

    # Validate against whitelist
    if actual_mime not in allowed_types:
        raise MimeTypeNotAllowedError(
            f"File type {actual_mime} is not allowed. " f"Allowed: {', '.join(allowed_types)}"
        )

    return actual_mime


def classify_document_type(filename: str, mime_type: str) -> str:
    """Classify document type based on filename and MIME type.

    Args:
        filename: Original filename (with extension)
        mime_type: MIME type of the file

    Returns:
        Document type string: supplier_declaration, invoice, shipment_note,
        geojson, certificate, or other
    """
    extension = Path(filename).suffix.lower()

    # Try extension mapping first
    if extension in EXTENSION_DOCUMENT_TYPE_MAP:
        return EXTENSION_DOCUMENT_TYPE_MAP[extension]

    # Try MIME type mapping
    if mime_type in MIME_TYPE_DOCUMENT_TYPE_MAP:
        return MIME_TYPE_DOCUMENT_TYPE_MAP[mime_type]

    # Default to 'other'
    return "other"


def generate_storage_path(case_id: UUID, filename: str, storage_root: str) -> str:
    """Generate storage path for a file and ensure uniqueness.

    Sanitizes filename to prevent path traversal attacks. Raises ValueError if
    the resolved path would escape the storage root.

    Args:
        case_id: UUID of the compliance case
        filename: Original filename
        storage_root: Root directory for storage

    Returns:
        Relative storage path (cases/{case_id}/{unique_filename})

    Raises:
        ValueError: If filename contains path separators or would escape storage root
    """
    # Sanitize: keep only the final path component, reject suspicious names
    safe_filename = Path(filename).name
    if not safe_filename or safe_filename in (".", ".."):
        safe_filename = "unnamed"

    case_dir = f"cases/{case_id}"
    relative_path = str(Path(case_dir) / safe_filename)

    # Resolve both paths to absolute for comparison
    full_path = (Path(storage_root) / relative_path).resolve()
    storage_root_resolved = Path(storage_root).resolve()

    # Enforce storage boundary — prevent escapes
    if not str(full_path).startswith(str(storage_root_resolved) + os.sep):
        raise ValueError(f"Resolved path escapes storage root: {full_path}")

    if full_path.exists():
        # Add numeric suffix to make unique
        stem = Path(safe_filename).stem
        suffix = Path(safe_filename).suffix
        counter = 1
        while True:
            new_filename = f"{stem}_{counter}{suffix}"
            new_relative_path = str(Path(case_dir) / new_filename)
            new_full_path = (Path(storage_root) / new_relative_path).resolve()
            if not new_full_path.exists():
                return new_relative_path
            counter += 1

    return relative_path


def store_file(file_content: bytes, storage_path: str, storage_root: str) -> None:
    """Store file on disk.

    Args:
        file_content: File content as bytes
        storage_path: Relative path within storage_root
        storage_root: Root directory for storage

    Raises:
        IOError: If file storage fails
    """
    full_path = Path(storage_root) / storage_path

    try:
        # Create directories if needed
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file
        with open(full_path, "wb") as f:
            f.write(file_content)

        logger.info(f"File stored at {full_path}")
    except OSError as e:
        logger.error(f"Failed to store file at {full_path}: {e}")
        raise OSError(f"Failed to store file: {e}") from e


def delete_stored_file(storage_path: str, storage_root: str) -> None:
    """Delete stored file (non-fatal if file doesn't exist).

    Args:
        storage_path: Relative path within storage_root
        storage_root: Root directory for storage
    """
    full_path = Path(storage_root) / storage_path

    try:
        if full_path.exists():
            full_path.unlink()
            logger.info(f"File deleted at {full_path}")
    except OSError as e:
        logger.warning(f"Failed to delete file at {full_path}: {e}")
