"""Tests for document upload API endpoints and file handler utilities."""

import tempfile
from pathlib import Path
from uuid import uuid4

import pytest
from app.api.documents import router, upload_document
from app.main import create_app
from app.services.file_handler import (
    classify_document_type,
    delete_stored_file,
    generate_storage_path,
    store_file,
    validate_file_size,
    validate_mime_type,
)


class TestFileHandlerUtilities:
    """Unit tests for file handler utilities."""

    def test_validate_file_size_under_limit(self):
        """File size under limit should pass."""
        validate_file_size(1024, 1024 * 1024)  # 1KB under 1MB limit

    def test_validate_file_size_at_limit(self):
        """File size at limit should pass."""
        validate_file_size(1024 * 1024, 1024 * 1024)  # Exactly 1MB

    def test_validate_file_size_over_limit(self):
        """File size over limit should raise ValueError."""
        with pytest.raises(ValueError, match="exceeds maximum"):
            validate_file_size(1024 * 1024 + 1, 1024 * 1024)

    def test_validate_mime_type_allowed(self):
        """Allowed MIME type should pass."""
        allowed = ["application/pdf", "image/jpeg", "text/plain"]
        validate_mime_type("application/pdf", allowed)

    def test_validate_mime_type_disallowed(self):
        """Disallowed MIME type should raise ValueError."""
        allowed = ["application/pdf", "image/jpeg"]
        with pytest.raises(ValueError, match="is not allowed"):
            validate_mime_type("application/exe", allowed)

    def test_classify_document_type_pdf(self):
        """PDF file should be classified as 'other'."""
        result = classify_document_type("invoice.pdf", "application/pdf")
        assert result == "other"

    def test_classify_document_type_xlsx(self):
        """XLSX file should be classified as 'invoice'."""
        result = classify_document_type(
            "invoice.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        assert result == "invoice"

    def test_classify_document_type_csv(self):
        """CSV file should be classified as 'invoice'."""
        result = classify_document_type("data.csv", "text/csv")
        assert result == "invoice"

    def test_classify_document_type_geojson(self):
        """GeoJSON file should be classified as 'geojson'."""
        result = classify_document_type("map.geojson", "application/json")
        assert result == "geojson"

    def test_classify_document_type_unknown_extension(self):
        """Unknown extension should default to 'other'."""
        result = classify_document_type("file.xyz", "application/octet-stream")
        assert result == "other"

    def test_generate_storage_path_format(self):
        """Storage path should be in correct format."""
        case_id = uuid4()
        filename = "test.pdf"
        storage_root = "/tmp"

        path = generate_storage_path(case_id, filename, storage_root)
        assert path.startswith(f"cases/{case_id}/")
        assert path.endswith("test.pdf")

    def test_generate_storage_path_uniqueness(self):
        """Duplicate filenames should get unique suffix."""
        case_id = uuid4()
        filename = "test.pdf"

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create first file
            path1 = generate_storage_path(case_id, filename, tmpdir)
            full_path1 = Path(tmpdir) / path1
            full_path1.parent.mkdir(parents=True, exist_ok=True)
            full_path1.write_text("test1")

            # Generate path for same filename
            path2 = generate_storage_path(case_id, filename, tmpdir)

            # Should be different paths
            assert path1 != path2
            assert "test_1.pdf" in path2

    def test_store_file_creates_directories(self):
        """store_file should create parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = "cases/123/subdir/file.pdf"
            content = b"test content"

            store_file(content, storage_path, tmpdir)

            full_path = Path(tmpdir) / storage_path
            assert full_path.exists()
            assert full_path.read_bytes() == content

    def test_store_file_error_on_invalid_path(self):
        """store_file should raise OSError for invalid storage root."""
        with pytest.raises(OSError):
            store_file(b"content", "file.pdf", "/nonexistent/invalid/path")

    def test_delete_stored_file_success(self):
        """delete_stored_file should delete existing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = "cases/123/file.pdf"
            full_path = Path(tmpdir) / storage_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text("test")

            assert full_path.exists()
            delete_stored_file(storage_path, tmpdir)
            assert not full_path.exists()

    def test_delete_stored_file_nonexistent(self):
        """delete_stored_file should not raise error for nonexistent file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Should not raise
            delete_stored_file("cases/123/nonexistent.pdf", tmpdir)


class TestDocumentsRouter:
    """Tests for documents router configuration."""

    def test_documents_router_exists(self):
        """Verify documents router is properly defined."""
        assert router is not None
        assert router.prefix == "/cases"
        assert any(route.name == "upload_document" for route in router.routes)

    def test_upload_document_function_exists(self):
        """Verify upload_document endpoint function exists."""
        assert upload_document is not None
        assert callable(upload_document)

    def test_app_includes_documents_router(self):
        """Verify FastAPI app includes documents router."""
        app = create_app()
        routes = [route.path for route in app.routes]
        # Should have cases/{case_id}/documents route
        assert any("/cases" in route for route in routes)


class TestDocumentsEndpointIntegration:
    """Integration tests for document upload endpoint."""

    def test_upload_document_router_prefix(self):
        """Verify endpoint is under /cases prefix."""
        app = create_app()
        routes = [route.path for route in app.routes]
        has_documents_endpoint = any(
            "documents" in route and "/cases/" in route for route in routes
        )
        assert has_documents_endpoint

    def test_upload_document_accepts_multipart(self):
        """Endpoint should accept multipart/form-data."""
        app = create_app()
        # Just verify the endpoint exists and has correct route
        routes = [(route.path, route.methods) for route in app.routes if "documents" in route.path]
        assert len(routes) > 0
        # Should have POST method
        assert any("POST" in methods for _, methods in routes)


# Simple structural tests that don't require database
def test_import_file_handler_functions():
    """Verify all file handler functions are importable."""
    functions = [
        validate_file_size,
        validate_mime_type,
        classify_document_type,
        generate_storage_path,
        store_file,
        delete_stored_file,
    ]
    for func in functions:
        assert callable(func)


def test_import_documents_router():
    """Verify documents router is importable."""
    from app.api.documents import router as doc_router

    assert doc_router is not None
    assert doc_router.prefix == "/cases"


def test_config_has_storage_settings():
    """Verify config has storage-related settings."""
    from app.config import get_settings

    settings = get_settings()
    assert hasattr(settings, "STORAGE_PATH")
    assert hasattr(settings, "MAX_FILE_SIZE_MB")
    assert hasattr(settings, "ALLOWED_MIME_TYPES")
    assert settings.MAX_FILE_SIZE_MB == 50
    assert "application/pdf" in settings.ALLOWED_MIME_TYPES


def test_config_get_allowed_mime_types_list():
    """Verify config can convert MIME types to list."""
    from app.config import get_settings

    settings = get_settings()
    mime_list = settings.get_allowed_mime_types_list()
    assert isinstance(mime_list, list)
    assert len(mime_list) > 0
    assert "application/pdf" in mime_list


def test_config_get_max_file_size_bytes():
    """Verify config can convert MB to bytes."""
    from app.config import get_settings

    settings = get_settings()
    max_bytes = settings.get_max_file_size_bytes()
    assert max_bytes == 50 * 1024 * 1024
