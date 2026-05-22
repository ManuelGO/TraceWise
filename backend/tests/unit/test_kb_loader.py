"""Unit tests for the KBLoader service."""

import json

import pytest

from app.services.kb_loader import KBLoader


class TestKBLoaderInitialization:
    """Tests for KBLoader initialization."""

    def test_init_default_path(self):
        """Test initializing with default path."""
        loader = KBLoader()
        assert loader.kb_path.exists()
        assert loader.index_path.exists()
        assert loader._index is not None

    def test_init_custom_path(self, tmp_path):
        """Test initializing with custom path."""
        loader = KBLoader(str(tmp_path))
        assert loader.kb_path == tmp_path
        assert loader._index is not None

    def test_init_missing_path(self):
        """Test initialization fails with missing path."""
        with pytest.raises(FileNotFoundError):
            KBLoader("/nonexistent/path")

    def test_creates_index_if_missing(self, tmp_path):
        """Test that loader creates new index if missing."""
        loader = KBLoader(str(tmp_path))
        assert loader._index is not None
        assert "documents" in loader._index
        assert "categories" in loader._index
        assert loader._index["version"] == "1.0"


class TestDocumentLoading:
    """Tests for loading individual documents."""

    def test_load_document_file_valid(self, tmp_path):
        """Test loading a valid document file."""
        # Create test document
        doc_content = """---
id: test-001
category: eudr_summaries
title: Test Document
description: A test document
tags:
  - test
created_at: 2026-05-21
updated_at: 2026-05-21
---

# Test Content

This is test content.
"""
        category_dir = tmp_path / "eudr_summaries"
        category_dir.mkdir()
        doc_file = category_dir / "test-001.md"
        doc_file.write_text(doc_content, encoding="utf-8")

        loader = KBLoader(str(tmp_path))
        result = loader._load_document_file(doc_file, "eudr_summaries")

        assert result is not None
        assert result["id"] == "test-001"
        assert result["category"] == "eudr_summaries"
        assert result["title"] == "Test Document"
        assert "path" in result

    def test_load_document_missing_frontmatter(self, tmp_path):
        """Test document without frontmatter is rejected."""
        doc_content = "# No frontmatter\n\nJust content."
        category_dir = tmp_path / "eudr_summaries"
        category_dir.mkdir()
        doc_file = category_dir / "test-001.md"
        doc_file.write_text(doc_content, encoding="utf-8")

        loader = KBLoader(str(tmp_path))
        result = loader._load_document_file(doc_file, "eudr_summaries")

        assert result is None
        assert len(loader.errors) > 0

    def test_load_document_invalid_yaml(self, tmp_path):
        """Test document with invalid YAML frontmatter."""
        doc_content = """---
id: test-001
invalid yaml: [unclosed list
---

Content
"""
        category_dir = tmp_path / "eudr_summaries"
        category_dir.mkdir()
        doc_file = category_dir / "test-001.md"
        doc_file.write_text(doc_content, encoding="utf-8")

        loader = KBLoader(str(tmp_path))
        result = loader._load_document_file(doc_file, "eudr_summaries")

        assert result is None
        assert len(loader.errors) > 0

    def test_load_document_missing_required_field(self, tmp_path):
        """Test document missing required metadata field."""
        doc_content = """---
id: test-001
title: Missing Description
tags: []
created_at: 2026-05-21
updated_at: 2026-05-21
---

Content
"""
        category_dir = tmp_path / "eudr_summaries"
        category_dir.mkdir()
        doc_file = category_dir / "test-001.md"
        doc_file.write_text(doc_content, encoding="utf-8")

        loader = KBLoader(str(tmp_path))
        result = loader._load_document_file(doc_file, "eudr_summaries")

        assert result is None
        assert len(loader.errors) > 0

    def test_load_document_category_mismatch(self, tmp_path):
        """Test document with category mismatch between frontmatter and directory."""
        doc_content = """---
id: test-001
category: regulatory_guidance
title: Test Document
description: Test
tags: []
created_at: 2026-05-21
updated_at: 2026-05-21
---

Content
"""
        category_dir = tmp_path / "eudr_summaries"
        category_dir.mkdir()
        doc_file = category_dir / "test-001.md"
        doc_file.write_text(doc_content, encoding="utf-8")

        loader = KBLoader(str(tmp_path))
        result = loader._load_document_file(doc_file, "eudr_summaries")

        assert result is None
        assert len(loader.errors) > 0

    def test_load_document_invalid_tags_type(self, tmp_path):
        """Test document with invalid tags (not a list)."""
        doc_content = """---
id: test-001
category: eudr_summaries
title: Test Document
description: Test
tags: "not-a-list"
created_at: 2026-05-21
updated_at: 2026-05-21
---

Content
"""
        category_dir = tmp_path / "eudr_summaries"
        category_dir.mkdir()
        doc_file = category_dir / "test-001.md"
        doc_file.write_text(doc_content, encoding="utf-8")

        loader = KBLoader(str(tmp_path))
        result = loader._load_document_file(doc_file, "eudr_summaries")

        assert result is None
        assert len(loader.errors) > 0


class TestCategoryLoading:
    """Tests for loading documents from categories."""

    def test_load_category(self, tmp_path):
        """Test loading all documents from a category."""
        # Create test documents
        category_dir = tmp_path / "eudr_summaries"
        category_dir.mkdir()

        for i in range(1, 4):
            doc_content = f"""---
id: eudr-{i:03d}
category: eudr_summaries
title: Test Document {i}
description: Test description {i}
tags:
  - test
created_at: 2026-05-21
updated_at: 2026-05-21
---

Content {i}
"""
            doc_file = category_dir / f"eudr-{i:03d}.md"
            doc_file.write_text(doc_content, encoding="utf-8")

        loader = KBLoader(str(tmp_path))
        docs = loader.load_category("eudr_summaries")

        assert len(docs) == 3
        assert all(doc["category"] == "eudr_summaries" for doc in docs)
        assert loader.loaded_count == 3

    def test_load_category_nonexistent(self, tmp_path):
        """Test loading non-existent category returns empty list."""
        loader = KBLoader(str(tmp_path))
        docs = loader.load_category("nonexistent")

        assert docs == []

    def test_load_category_skips_gitkeep(self, tmp_path):
        """Test that .gitkeep files are skipped."""
        category_dir = tmp_path / "eudr_summaries"
        category_dir.mkdir()
        (category_dir / ".gitkeep").touch()

        doc_content = """---
id: test-001
category: eudr_summaries
title: Test Document
description: Test
tags: []
created_at: 2026-05-21
updated_at: 2026-05-21
---

Content
"""
        (category_dir / "test-001.md").write_text(doc_content, encoding="utf-8")

        loader = KBLoader(str(tmp_path))
        docs = loader.load_category("eudr_summaries")

        assert len(docs) == 1
        assert docs[0]["id"] == "test-001"


class TestLoadAll:
    """Tests for loading all documents."""

    def test_load_all_multiple_categories(self, tmp_path):
        """Test loading all documents from all categories."""
        # Create documents in multiple categories
        for category in ["eudr_summaries", "regulatory_guidance"]:
            category_dir = tmp_path / category
            category_dir.mkdir()

            for i in range(1, 3):
                doc_content = f"""---
id: {category}-{i:03d}
category: {category}
title: Test Document {i}
description: Test description {i}
tags: []
created_at: 2026-05-21
updated_at: 2026-05-21
---

Content {i}
"""
                doc_file = category_dir / f"{category}-{i:03d}.md"
                doc_file.write_text(doc_content, encoding="utf-8")

        loader = KBLoader(str(tmp_path))
        docs = loader.load_all()

        assert len(docs) == 4
        assert loader.loaded_count == 4

    def test_load_all_idempotency(self, tmp_path):
        """Test that loading twice doesn't duplicate documents."""
        category_dir = tmp_path / "eudr_summaries"
        category_dir.mkdir()

        doc_content = """---
id: test-001
category: eudr_summaries
title: Test Document
description: Test
tags: []
created_at: 2026-05-21
updated_at: 2026-05-21
---

Content
"""
        (category_dir / "test-001.md").write_text(doc_content, encoding="utf-8")

        loader = KBLoader(str(tmp_path))
        loader.load_all()
        assert loader.loaded_count == 1

        # Load again
        docs2 = loader.load_all()
        assert loader.skipped_count > 0
        assert len(docs2) == 0  # Second load returns nothing (already exists)

    def test_load_all_skips_hidden_dirs(self, tmp_path):
        """Test that hidden directories are skipped."""
        (tmp_path / ".hidden").mkdir()
        (tmp_path / "eudr_summaries").mkdir()

        # Add document to regular directory
        doc_content = """---
id: test-001
category: eudr_summaries
title: Test
description: Test
tags: []
created_at: 2026-05-21
updated_at: 2026-05-21
---

Content
"""
        (tmp_path / "eudr_summaries" / "test-001.md").write_text(
            doc_content, encoding="utf-8"
        )

        loader = KBLoader(str(tmp_path))
        docs = loader.load_all()

        assert len(docs) == 1


class TestIndexManagement:
    """Tests for index management."""

    def test_save_index(self, tmp_path):
        """Test saving index to file."""
        category_dir = tmp_path / "eudr_summaries"
        category_dir.mkdir()

        doc_content = """---
id: test-001
category: eudr_summaries
title: Test Document
description: Test
tags: []
created_at: 2026-05-21
updated_at: 2026-05-21
---

Content
"""
        (category_dir / "test-001.md").write_text(doc_content, encoding="utf-8")

        loader = KBLoader(str(tmp_path))
        loader.load_all()
        success = loader.save_index()

        assert success
        assert loader.index_path.exists()

        # Verify saved content
        with open(loader.index_path, encoding="utf-8") as f:
            saved_index = json.load(f)

        assert len(saved_index["documents"]) == 1
        assert saved_index["documents"][0]["id"] == "test-001"
        assert saved_index["last_updated"] is not None

    def test_update_category_counts(self, tmp_path):
        """Test category count update."""
        category_dir = tmp_path / "eudr_summaries"
        category_dir.mkdir()

        for i in range(1, 4):
            doc_content = f"""---
id: eudr-{i:03d}
category: eudr_summaries
title: Test Document {i}
description: Test
tags: []
created_at: 2026-05-21
updated_at: 2026-05-21
---

Content {i}
"""
            (category_dir / f"eudr-{i:03d}.md").write_text(doc_content, encoding="utf-8")

        loader = KBLoader(str(tmp_path))
        loader.load_all()
        loader.update_category_counts()

        assert loader._index["categories"]["eudr_summaries"]["document_count"] == 3

    def test_validate_index(self, tmp_path):
        """Test index validation."""
        loader = KBLoader(str(tmp_path))
        assert loader.validate_index()

        # Break the index
        loader._index = None
        assert not loader.validate_index()

        loader._index = {}
        assert not loader.validate_index()


class TestErrorHandling:
    """Tests for error handling and recovery."""

    def test_continue_on_individual_errors(self, tmp_path):
        """Test that loader continues after individual document errors."""
        category_dir = tmp_path / "eudr_summaries"
        category_dir.mkdir()

        # Valid document
        valid_doc = """---
id: valid-001
category: eudr_summaries
title: Valid Document
description: Valid
tags: []
created_at: 2026-05-21
updated_at: 2026-05-21
---

Content
"""
        (category_dir / "valid-001.md").write_text(valid_doc, encoding="utf-8")

        # Invalid document (missing frontmatter)
        invalid_doc = "# No frontmatter\n\nContent"
        (category_dir / "invalid-001.md").write_text(invalid_doc, encoding="utf-8")

        # Another valid document
        valid_doc2 = """---
id: valid-002
category: eudr_summaries
title: Valid Document 2
description: Valid
tags: []
created_at: 2026-05-21
updated_at: 2026-05-21
---

Content
"""
        (category_dir / "valid-002.md").write_text(valid_doc2, encoding="utf-8")

        loader = KBLoader(str(tmp_path))
        docs = loader.load_all()

        # Should have 2 valid documents despite 1 error
        assert len(docs) == 2
        assert loader.loaded_count == 2
        assert len(loader.errors) == 1

    def test_get_statistics(self, tmp_path):
        """Test retrieving loading statistics."""
        category_dir = tmp_path / "eudr_summaries"
        category_dir.mkdir()

        doc_content = """---
id: test-001
category: eudr_summaries
title: Test
description: Test
tags: []
created_at: 2026-05-21
updated_at: 2026-05-21
---

Content
"""
        (category_dir / "test-001.md").write_text(doc_content, encoding="utf-8")

        loader = KBLoader(str(tmp_path))
        loader.load_all()

        stats = loader.get_statistics()

        assert stats["loaded"] == 1
        assert stats["skipped"] == 0
        assert stats["errors"] == 0
        assert isinstance(stats["error_messages"], list)


class TestIntegrationWithKnowledgeBase:
    """Integration tests with KnowledgeBase service."""

    def test_loaded_documents_are_readable(self, tmp_path):
        """Test that loaded documents can be read by KnowledgeBase."""
        from app.services import KnowledgeBase

        # Setup: Create and load documents
        category_dir = tmp_path / "eudr_summaries"
        category_dir.mkdir()

        doc_content = """---
id: test-001
category: eudr_summaries
title: Test Document
description: Test description
tags:
  - test
created_at: 2026-05-21
updated_at: 2026-05-21
source: "https://test.com"
version: "1.0"
related_documents: []
---

# Test Content

This is test content for searching.
"""
        (category_dir / "test-001.md").write_text(doc_content, encoding="utf-8")

        # Load with KBLoader
        loader = KBLoader(str(tmp_path))
        loader.load_all()
        loader.save_index()

        # Verify with KnowledgeBase
        kb = KnowledgeBase(str(tmp_path))
        doc = kb.get_document("test-001")

        assert doc is not None
        assert doc.title == "Test Document"
        assert doc.category == "eudr_summaries"

    def test_loaded_documents_are_searchable(self, tmp_path):
        """Test that loaded documents are searchable."""
        from app.services import KnowledgeBase

        category_dir = tmp_path / "eudr_summaries"
        category_dir.mkdir()

        doc_content = """---
id: test-001
category: eudr_summaries
title: EUDR Compliance
description: Compliance requirements
tags:
  - compliance
  - eudr
created_at: 2026-05-21
updated_at: 2026-05-21
source: "https://test.com"
version: "1.0"
related_documents: []
---

# EUDR Compliance

Deforestation prevention is a key requirement.
"""
        (category_dir / "test-001.md").write_text(doc_content, encoding="utf-8")

        loader = KBLoader(str(tmp_path))
        loader.load_all()
        loader.save_index()

        kb = KnowledgeBase(str(tmp_path))
        results = kb.search_documents("deforestation")

        assert len(results) > 0
        assert results[0].id == "test-001"
