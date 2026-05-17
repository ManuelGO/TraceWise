"""Unit tests for text extraction service."""

from pathlib import Path

import pytest

from app.services.text_extractor import (
    ExtractionError,
    extract_from_csv,
    extract_from_docx,
    extract_from_pdf,
    extract_from_txt,
    extract_from_xlsx,
)

SAMPLES_DIR = Path(__file__).parent.parent / "samples"


class TestExtractFromPdf:
    """Tests for PDF text extraction."""

    def test_extract_from_pdf_success(self):
        """Test successful text extraction from PDF."""
        pdf_path = SAMPLES_DIR / "sample.pdf"
        if not pdf_path.exists():
            pytest.skip("Sample PDF not found")

        file_bytes = pdf_path.read_bytes()
        text, page_count = extract_from_pdf(file_bytes)

        assert isinstance(text, str)
        assert len(text) > 0
        assert isinstance(page_count, int)
        assert page_count > 0

    def test_extract_from_pdf_empty(self):
        """Test extraction from empty PDF raises error."""
        empty_pdf = b"%PDF-1.4\n%EOF"

        text, page_count = extract_from_pdf(empty_pdf)

        assert isinstance(text, str)
        assert isinstance(page_count, int)

    def test_extract_from_pdf_corrupted(self):
        """Test extraction from corrupted PDF raises ExtractionError."""
        corrupted_pdf = b"Not a PDF file at all"

        with pytest.raises(ExtractionError):
            extract_from_pdf(corrupted_pdf)


class TestExtractFromDocx:
    """Tests for DOCX text extraction."""

    def test_extract_from_docx_success(self):
        """Test successful text extraction from DOCX."""
        docx_path = SAMPLES_DIR / "sample.docx"
        if not docx_path.exists():
            pytest.skip("Sample DOCX not found")

        file_bytes = docx_path.read_bytes()
        text = extract_from_docx(file_bytes)

        assert isinstance(text, str)
        assert len(text) > 0
        assert "Sample" in text or "DOCX" in text or "paragraph" in text

    def test_extract_from_docx_corrupted(self):
        """Test extraction from corrupted DOCX raises ExtractionError."""
        corrupted_docx = b"Not a DOCX file"

        with pytest.raises(ExtractionError):
            extract_from_docx(corrupted_docx)


class TestExtractFromCsv:
    """Tests for CSV text extraction."""

    def test_extract_from_csv_success(self):
        """Test successful text extraction from CSV."""
        csv_path = SAMPLES_DIR / "sample.csv"
        if not csv_path.exists():
            pytest.skip("Sample CSV not found")

        file_bytes = csv_path.read_bytes()
        text = extract_from_csv(file_bytes)

        assert isinstance(text, str)
        assert len(text) > 0
        assert "name" in text.lower() or "Alice" in text

    def test_extract_from_csv_with_special_chars(self):
        """Test CSV extraction with special characters."""
        csv_content = b"col1,col2\nvalue1,value with comma\n"
        text = extract_from_csv(csv_content)

        assert isinstance(text, str)
        assert len(text) > 0


class TestExtractFromXlsx:
    """Tests for XLSX text extraction."""

    def test_extract_from_xlsx_success(self):
        """Test successful text extraction from XLSX."""
        xlsx_path = SAMPLES_DIR / "sample.xlsx"
        if not xlsx_path.exists():
            pytest.skip("Sample XLSX not found")

        file_bytes = xlsx_path.read_bytes()
        text = extract_from_xlsx(file_bytes)

        assert isinstance(text, str)
        assert len(text) > 0
        assert "===" in text or "Sheet" in text or "Alice" in text

    def test_extract_from_xlsx_corrupted(self):
        """Test extraction from corrupted XLSX raises ExtractionError."""
        corrupted_xlsx = b"Not an XLSX file"

        with pytest.raises(ExtractionError):
            extract_from_xlsx(corrupted_xlsx)


class TestExtractFromTxt:
    """Tests for TXT text extraction."""

    def test_extract_from_txt_utf8(self):
        """Test extraction from UTF-8 text file."""
        txt_path = SAMPLES_DIR / "sample.txt"
        if not txt_path.exists():
            pytest.skip("Sample TXT not found")

        file_bytes = txt_path.read_bytes()
        text = extract_from_txt(file_bytes)

        assert isinstance(text, str)
        assert len(text) > 0

    def test_extract_from_txt_with_invalid_bytes(self):
        """Test extraction with invalid UTF-8 bytes (uses replacement)."""
        # Valid UTF-8 with some invalid bytes mixed in
        file_bytes = b"Valid text\xff\xfeInvalid bytes"
        text = extract_from_txt(file_bytes)

        assert isinstance(text, str)
        assert "Valid text" in text
        assert "?" in text or "Invalid" in text

    def test_extract_from_txt_empty(self):
        """Test extraction from empty text file."""
        file_bytes = b""
        text = extract_from_txt(file_bytes)

        assert isinstance(text, str)
        assert len(text) == 0


class TestExtractionErrorHandling:
    """Tests for ExtractionError exception."""

    def test_extraction_error_creation(self):
        """Test ExtractionError can be created."""
        error = ExtractionError("Test error message")
        assert str(error) == "Test error message"

    def test_extraction_error_is_exception(self):
        """Test ExtractionError is an Exception."""
        error = ExtractionError("Test")
        assert isinstance(error, Exception)
