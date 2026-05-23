"""Integration tests for text extraction Celery task."""

from pathlib import Path

import pytest


@pytest.fixture
def sample_pdf_bytes():
    """Load sample PDF for testing."""
    samples_dir = Path(__file__).parent.parent / "samples"
    pdf_path = samples_dir / "sample.pdf"
    if pdf_path.exists():
        return pdf_path.read_bytes()
    return None


@pytest.fixture
def sample_txt_bytes():
    """Load sample TXT for testing."""
    samples_dir = Path(__file__).parent.parent / "samples"
    txt_path = samples_dir / "sample.txt"
    if txt_path.exists():
        return txt_path.read_bytes()
    return None


class TestExtractTextTask:
    """Tests for extract_text_task Celery integration."""

    @pytest.mark.asyncio
    async def test_task_configuration(self):
        """Test extract_text_task is correctly configured."""
        from app.tasks.document_tasks import extract_text_task

        assert extract_text_task.name == "app.tasks.document_tasks.extract_text_task"
        assert extract_text_task.autoretry_for == (Exception,)
        assert extract_text_task.max_retries == 3

    @pytest.mark.asyncio
    async def test_task_has_retry_backoff(self):
        """Test extract_text_task has exponential backoff configured."""
        from app.tasks.document_tasks import extract_text_task

        assert extract_text_task.retry_backoff is True
        assert extract_text_task.retry_backoff_max == 600
        assert extract_text_task.retry_jitter is True

    @pytest.mark.asyncio
    async def test_task_can_be_enqueued(self):
        """Test that extract_text_task can be enqueued."""
        from app.tasks.document_tasks import extract_text_task

        assert hasattr(extract_text_task, "delay")
        assert callable(extract_text_task.delay)

    def test_task_imports(self):
        """Test that task can be imported without errors."""
        from app.tasks.document_tasks import extract_text_task

        assert extract_text_task is not None

    def test_extraction_services_imported(self):
        """Test that extraction services can be imported."""
        from app.services.text_extractor import (
            ExtractionError,
            extract_from_csv,
            extract_from_docx,
            extract_from_pdf,
            extract_from_txt,
            extract_from_xlsx,
        )

        assert all(
            [
                extract_from_pdf,
                extract_from_docx,
                extract_from_csv,
                extract_from_xlsx,
                extract_from_txt,
                ExtractionError,
            ]
        )

    def test_chunker_service_imported(self):
        """Test that chunker service can be imported."""
        from app.services.text_chunker import TextChunker, ChunkingConfig

        assert TextChunker is not None
        assert ChunkingConfig is not None

    def test_document_extraction_model_imported(self):
        """Test that DocumentExtraction model can be imported."""
        from app.models import DocumentExtraction

        assert DocumentExtraction is not None

    def test_document_extraction_repository_imported(self):
        """Test that DocumentExtractionRepository can be imported."""
        from app.db.repositories.document_extraction import DocumentExtractionRepository

        assert DocumentExtractionRepository is not None

    def test_job_type_has_extract_text(self):
        """Test that JobType enum includes EXTRACT_TEXT."""
        from app.models.enums import JobType

        assert hasattr(JobType, "EXTRACT_TEXT")
        assert JobType.EXTRACT_TEXT.value == "extract_text"

    @pytest.mark.asyncio
    async def test_extraction_task_with_sample_pdf(self, sample_pdf_bytes):
        """Test extraction logic can process sample PDF."""
        if not sample_pdf_bytes:
            pytest.skip("Sample PDF not available")

        from app.services.text_extractor import extract_from_pdf

        text, pages = extract_from_pdf(sample_pdf_bytes)

        assert isinstance(text, str)
        assert len(text) > 0
        assert isinstance(pages, int)
        assert pages > 0

    @pytest.mark.asyncio
    async def test_extraction_task_with_sample_txt(self, sample_txt_bytes):
        """Test extraction logic can process sample TXT."""
        if not sample_txt_bytes:
            pytest.skip("Sample TXT not available")

        from app.services.text_extractor import extract_from_txt

        text = extract_from_txt(sample_txt_bytes)

        assert isinstance(text, str)
        assert len(text) > 0

    def test_chunking_works_end_to_end(self):
        """Test chunking with extracted-like content."""
        from app.services.text_chunker import TextChunker

        sample_text = "word " * 200
        chunker = TextChunker(chunk_size=512, overlap=50, strategy="simple")
        chunks = chunker.chunk(sample_text)

        assert len(chunks) > 0
        assert all(isinstance(c["text"], str) for c in chunks)
        assert all(isinstance(c["index"], int) for c in chunks)
        assert all(c["page"] is None for c in chunks)
