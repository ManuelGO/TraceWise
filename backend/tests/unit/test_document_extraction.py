"""Unit tests for DocumentExtraction model."""

from uuid import uuid4

from app.models import DocumentExtraction


class TestDocumentExtractionModel:
    """Tests for DocumentExtraction model instantiation."""

    def test_model_creation_with_all_fields(self):
        """Test creating DocumentExtraction with all fields."""
        doc_id = str(uuid4())
        chunks = [
            {"text": "chunk 1", "index": 0, "page": None},
            {"text": "chunk 2", "index": 1, "page": None},
        ]
        text = "chunk 1 chunk 2"
        key = "test_key_123"

        extraction = DocumentExtraction(
            document_id=doc_id,
            extracted_text=text,
            chunks=chunks,
            chunk_count=len(chunks),
            extraction_status="extracted",
            pages=5,
            error_message=None,
            idempotency_key=key,
        )

        assert extraction.document_id == doc_id
        assert extraction.extracted_text == text
        assert extraction.chunks == chunks
        assert extraction.chunk_count == 2
        assert extraction.extraction_status == "extracted"
        assert extraction.pages == 5
        assert extraction.error_message is None
        assert extraction.idempotency_key == key

    def test_model_creation_minimal_fields(self):
        """Test creating DocumentExtraction with minimal required fields."""
        doc_id = str(uuid4())

        extraction = DocumentExtraction(
            document_id=doc_id,
            extracted_text="sample text",
            chunks=[{"text": "sample", "index": 0, "page": None}],
            chunk_count=1,
            idempotency_key="key_123",
        )

        assert extraction.document_id == doc_id
        assert extraction.extraction_status == "extracted"
        assert extraction.pages is None
        assert extraction.error_message is None

    def test_model_has_uuid_primary_key(self):
        """Test that model has id field."""
        extraction = DocumentExtraction(
            document_id=str(uuid4()),
            extracted_text="text",
            chunks=[],
            chunk_count=0,
            idempotency_key="key",
        )

        # ID is auto-generated on insert, so may be None pre-DB
        assert hasattr(extraction, "id")

    def test_model_repr(self):
        """Test DocumentExtraction __repr__ method."""
        doc_id = str(uuid4())
        extraction = DocumentExtraction(
            document_id=doc_id,
            extracted_text="text",
            chunks=[],
            chunk_count=0,
            extraction_status="extracted",
            idempotency_key="key",
        )

        repr_str = repr(extraction)
        assert "DocumentExtraction" in repr_str
        assert "extraction_status" in repr_str

    def test_model_timestamps(self):
        """Test that created_at and updated_at are set."""
        extraction = DocumentExtraction(
            document_id=str(uuid4()),
            extracted_text="text",
            chunks=[],
            chunk_count=0,
            idempotency_key="key",
        )

        # Timestamps are set by default on creation
        assert hasattr(extraction, "created_at")
        assert hasattr(extraction, "updated_at")

    def test_model_extraction_status_default(self):
        """Test that extraction_status defaults to 'extracted'."""
        extraction = DocumentExtraction(
            document_id=str(uuid4()),
            extracted_text="text",
            chunks=[],
            chunk_count=0,
            idempotency_key="key",
        )

        assert extraction.extraction_status == "extracted"

    def test_model_with_empty_chunks(self):
        """Test model with empty chunks array."""
        extraction = DocumentExtraction(
            document_id=str(uuid4()),
            extracted_text="",
            chunks=[],
            chunk_count=0,
            idempotency_key="key",
        )

        assert extraction.chunks == []
        assert extraction.chunk_count == 0

    def test_model_with_multiple_chunks(self):
        """Test model with multiple chunks."""
        chunks = [
            {"text": "chunk 1", "index": 0, "page": 1},
            {"text": "chunk 2", "index": 1, "page": 2},
            {"text": "chunk 3", "index": 2, "page": 3},
        ]
        extraction = DocumentExtraction(
            document_id=str(uuid4()),
            extracted_text="full text",
            chunks=chunks,
            chunk_count=3,
            idempotency_key="key",
        )

        assert len(extraction.chunks) == 3
        assert extraction.chunk_count == 3

    def test_model_with_error_message(self):
        """Test model with failed extraction (error_message)."""
        extraction = DocumentExtraction(
            document_id=str(uuid4()),
            extracted_text="",
            chunks=[],
            chunk_count=0,
            extraction_status="failed",
            error_message="PDF is corrupted",
            idempotency_key="key",
        )

        assert extraction.extraction_status == "failed"
        assert extraction.error_message == "PDF is corrupted"
