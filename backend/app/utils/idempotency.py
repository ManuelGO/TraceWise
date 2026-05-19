"""Idempotency key generation for deduplication in task processing."""

import hashlib
import json
from uuid import UUID


def generate_idempotency_key(document_id: UUID, job_type: str, job_metadata: dict[str, object]) -> str:
    """Generate a deterministic idempotency key for task deduplication.

    Combines document_id, job_type, and job_metadata into a SHA256 hash.
    Same inputs always produce the same key, enabling deduplication on retry.

    Args:
        document_id: UUID of the document being processed
        job_type: Type of job (e.g., "extract_text")
        job_metadata: Dictionary of job-specific metadata (must be JSON-serializable)

    Returns:
        64-character hex string (SHA256 digest, always lowercase)

    Note:
        Metadata is serialized with sorted keys (deterministic JSON) and UTF-8 encoding.
        This ensures identical inputs always produce identical keys regardless of dict order.

    Example:
        >>> doc_id = UUID('550e8400-e29b-41d4-a716-446655440000')
        >>> key = generate_idempotency_key(doc_id, 'extract_text', {'page_range': [1, 10]})
        >>> len(key)
        64
        >>> all(c in '0123456789abcdef' for c in key)
        True
    """
    # Serialize metadata with sorted keys for determinism
    metadata_json = json.dumps(job_metadata, sort_keys=True)

    # Combine inputs with delimiter
    combined = f"{document_id}:{job_type}:{metadata_json}"

    # Generate SHA256 hash
    hash_digest = hashlib.sha256(combined.encode()).hexdigest()

    return hash_digest


__all__ = ["generate_idempotency_key"]
