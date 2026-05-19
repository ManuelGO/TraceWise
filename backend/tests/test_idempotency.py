"""Tests for idempotency key generation and deduplication (Task 27)."""

from uuid import UUID, uuid4

from app.utils.idempotency import generate_idempotency_key


class TestIdempotencyKeyGeneration:
    """Test idempotency key generation determinism and uniqueness."""

    def test_key_generation_deterministic(self):
        """Verify identical inputs produce identical keys."""
        doc_id = UUID("550e8400-e29b-41d4-a716-446655440000")
        job_type = "extract_text"
        metadata = {"document_id": str(doc_id), "page_range": [1, 10]}

        key1 = generate_idempotency_key(doc_id, job_type, metadata)
        key2 = generate_idempotency_key(doc_id, job_type, metadata)

        assert key1 == key2

    def test_key_generation_format(self):
        """Verify key is 64-character hex string."""
        doc_id = uuid4()
        job_type = "extract_text"
        metadata = {}

        key = generate_idempotency_key(doc_id, job_type, metadata)

        assert isinstance(key, str)
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_key_uniqueness_different_document_id(self):
        """Different document_id produces different key."""
        doc_id_1 = UUID("550e8400-e29b-41d4-a716-446655440000")
        doc_id_2 = UUID("550e8400-e29b-41d4-a716-446655440001")
        job_type = "extract_text"
        metadata = {"page_range": [1, 10]}

        key1 = generate_idempotency_key(doc_id_1, job_type, metadata)
        key2 = generate_idempotency_key(doc_id_2, job_type, metadata)

        assert key1 != key2

    def test_key_uniqueness_different_job_type(self):
        """Different job_type produces different key."""
        doc_id = uuid4()
        metadata = {"page_range": [1, 10]}

        key1 = generate_idempotency_key(doc_id, "extract_text", metadata)
        key2 = generate_idempotency_key(doc_id, "extract_entities", metadata)

        assert key1 != key2

    def test_key_uniqueness_different_metadata(self):
        """Different metadata produces different key."""
        doc_id = uuid4()
        job_type = "extract_text"
        metadata1 = {"page_range": [1, 10]}
        metadata2 = {"page_range": [1, 20]}

        key1 = generate_idempotency_key(doc_id, job_type, metadata1)
        key2 = generate_idempotency_key(doc_id, job_type, metadata2)

        assert key1 != key2

    def test_key_deterministic_with_metadata_order(self):
        """Verify metadata key order doesn't affect determinism (sorted internally)."""
        doc_id = uuid4()
        job_type = "extract_text"

        # Same content, different insertion order
        metadata1 = {"z_field": 1, "a_field": 2}
        metadata2 = {"a_field": 2, "z_field": 1}

        key1 = generate_idempotency_key(doc_id, job_type, metadata1)
        key2 = generate_idempotency_key(doc_id, job_type, metadata2)

        # Both should produce same key due to sorted keys in JSON
        assert key1 == key2

    def test_key_uniqueness_nested_metadata(self):
        """Verify nested metadata differences produce different keys."""
        doc_id = uuid4()
        job_type = "extract_text"
        metadata1 = {"config": {"ocr": True}}
        metadata2 = {"config": {"ocr": False}}

        key1 = generate_idempotency_key(doc_id, job_type, metadata1)
        key2 = generate_idempotency_key(doc_id, job_type, metadata2)

        assert key1 != key2

    def test_key_empty_metadata(self):
        """Verify empty metadata produces valid key."""
        doc_id = uuid4()
        job_type = "extract_text"
        metadata = {}

        key = generate_idempotency_key(doc_id, job_type, metadata)

        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_key_special_characters_in_metadata(self):
        """Verify special characters in metadata are handled correctly."""
        doc_id = uuid4()
        job_type = "extract_text"
        metadata = {"filename": "test_doc-2024_v1.pdf", "path": "/home/user/docs"}

        key = generate_idempotency_key(doc_id, job_type, metadata)

        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_key_deterministic_across_calls(self):
        """Verify key generation is deterministic across multiple calls."""
        doc_id = UUID("550e8400-e29b-41d4-a716-446655440000")
        job_type = "extract_text"
        metadata = {"page_range": [1, 10], "ocr": True}

        keys = [generate_idempotency_key(doc_id, job_type, metadata) for _ in range(5)]

        # All keys should be identical
        assert all(k == keys[0] for k in keys)

    def test_key_with_enum_job_type(self):
        """Verify key generation works with enum job types (converted to string)."""
        from enum import StrEnum

        class JobType(StrEnum):
            EXTRACT_TEXT = "extract_text"
            VALIDATE_DOCUMENT = "validate_document"

        doc_id = uuid4()
        job_type_enum = JobType.EXTRACT_TEXT
        metadata = {"page_range": [1, 10]}

        # Should convert enum to string and generate valid key
        key = generate_idempotency_key(doc_id, str(job_type_enum), metadata)

        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_key_deterministic_with_enum_value(self):
        """Verify enum.value produces same key as direct string."""
        from enum import StrEnum

        class JobType(StrEnum):
            EXTRACT_TEXT = "extract_text"

        doc_id = uuid4()
        metadata = {"page_range": [1, 10]}

        # Use .value to extract the string value, not str() which may include enum class
        key_enum = generate_idempotency_key(doc_id, JobType.EXTRACT_TEXT.value, metadata)
        key_string = generate_idempotency_key(doc_id, "extract_text", metadata)

        assert key_enum == key_string
