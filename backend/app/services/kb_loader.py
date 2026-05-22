"""Service for loading and managing knowledge base documents."""

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

MAX_DOC_SIZE = 1 * 1024 * 1024  # 1 MB document size limit


class KBLoader:
    """Service for loading documents into the knowledge base.

    Handles loading documents from the filesystem, validating metadata,
    updating the index.json file, and ensuring idempotency.

    Security Notes:
    - Metadata is validated for type and length to prevent injection attacks.
    - Symlinks pointing outside KB directory are rejected via path validation.
    - Document size is limited to 1 MB to prevent DOS attacks.
    - KB path should only be instantiated with operator-controlled or hardcoded values.
    """

    def __init__(self, kb_path: str | None = None):
        """Initialize the KB loader.

        Args:
            kb_path: Path to knowledge base directory. If None, uses default path.

        Raises:
            FileNotFoundError: If knowledge base directory doesn't exist.
        """
        if kb_path is None:
            kb_path = str(Path(__file__).parent.parent / "data" / "knowledge_base")

        self.kb_path = Path(kb_path)
        if not self.kb_path.exists():
            raise FileNotFoundError(f"Knowledge base path not found: {self.kb_path}")

        self.index_path = self.kb_path / "index.json"
        self._load_or_create_index()
        self.errors: list[str] = []
        self.loaded_count = 0
        self.skipped_count = 0

    def _load_or_create_index(self) -> None:
        """Load existing index.json or create a new one if missing.

        Raises:
            ValueError: If index.json exists but is invalid JSON.
        """
        if self.index_path.exists():
            try:
                with open(self.index_path, encoding="utf-8") as f:
                    self._index = json.load(f)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse index.json: {e}")
                raise ValueError(f"Invalid JSON in index.json: {e}") from e
        else:
            self._index = {
                "version": "1.0",
                "last_updated": datetime.now(UTC).isoformat(),
                "documents": [],
                "categories": {
                    "eudr_summaries": {
                        "name": "EUDR Summaries",
                        "description": "EUDR regulation summaries and overviews",
                        "document_count": 0,
                    },
                    "regulatory_guidance": {
                        "name": "Regulatory Guidance",
                        "description": "Guidance for implementing regulatory requirements",
                        "document_count": 0,
                    },
                    "documentation_requirements": {
                        "name": "Documentation Requirements",
                        "description": "Required documentation and record-keeping",
                        "document_count": 0,
                    },
                    "risk_assessment_guidance": {
                        "name": "Risk Assessment Guidance",
                        "description": "Guidance for assessing deforestation risks",
                        "document_count": 0,
                    },
                    "traceability_obligations": {
                        "name": "Traceability Obligations",
                        "description": "Supply chain traceability requirements",
                        "document_count": 0,
                    },
                },
            }
            logger.info("Created new index structure")

    def load_category(self, category: str) -> list[dict[str, Any]]:
        """Load all documents from a specific category directory.

        Args:
            category: Category name (directory name under kb_path).

        Returns:
            List of loaded document metadata dictionaries.
        """
        category_path = self.kb_path / category
        if not category_path.exists():
            logger.warning(f"Category directory not found: {category_path}")
            return []

        loaded = []
        for doc_file in sorted(category_path.glob("*.md")):
            if doc_file.name == ".gitkeep" or doc_file.name.startswith("."):
                continue

            doc_meta = self._load_document_file(doc_file, category)
            if doc_meta:
                loaded.append(doc_meta)

        return loaded

    def load_all(self) -> list[dict[str, Any]]:
        """Load all documents from all category directories.

        Returns:
            List of all loaded document metadata dictionaries.
        """
        all_loaded = []
        for category_dir in sorted(self.kb_path.iterdir()):
            if not category_dir.is_dir() or category_dir.name.startswith("."):
                continue

            # FIX #11: Removed dead code - is_dir() already excludes files

            category_docs = self.load_category(category_dir.name)
            all_loaded.extend(category_docs)

        return all_loaded

    def _load_document_file(
        self, doc_path: Path, category: str
    ) -> dict[str, Any] | None:
        """Load and parse a single document file.

        Args:
            doc_path: Path to document file.
            category: Category the document belongs to.

        Returns:
            Document metadata dict if valid, None otherwise.
        """
        try:
            # FIX #1: Security check FIRST, before any file I/O
            try:
                doc_path.resolve().relative_to(self.kb_path.resolve())
            except ValueError:
                error = f"Path traversal blocked: {doc_path.name}"
                logger.warning(error)
                self.errors.append(error)
                return None

            # FIX #7: Check file size BEFORE reading
            try:
                file_size = doc_path.stat().st_size
            except OSError as e:
                error = f"Cannot stat file {doc_path.name}: {e}"
                logger.warning(error)
                self.errors.append(error)
                return None

            if file_size > MAX_DOC_SIZE:
                error = f"Document too large ({file_size} bytes): {doc_path.name}"
                logger.warning(error)
                self.errors.append(error)
                return None

            # NOW safe to read the file
            with open(doc_path, encoding="utf-8") as f:
                content = f.read()

            # FIX #2: Normalize line endings (CRLF → LF)
            content = content.replace("\r\n", "\n").replace("\r", "\n")

            # Parse frontmatter
            if not content.startswith("---"):
                error = f"Missing frontmatter in {doc_path.name}"
                logger.warning(error)
                self.errors.append(error)
                return None

            parts = re.split(r"^---$", content, maxsplit=2, flags=re.MULTILINE)
            if len(parts) < 3:
                error = f"Invalid frontmatter in {doc_path.name}"
                logger.warning(error)
                self.errors.append(error)
                return None

            frontmatter_str = parts[1].strip()
            metadata = yaml.safe_load(frontmatter_str)

            # Validate metadata
            if not self._validate_document_metadata(metadata, doc_path.name):
                return None

            doc_id = metadata.get("id", "")
            doc_category = metadata.get("category", "")

            # Check idempotency: skip if already in index
            if self._document_exists(doc_id):
                logger.debug(f"Document already in index, skipping: {doc_id}")
                self.skipped_count += 1
                return None

            # Validate category matches
            if doc_category != category:
                error = f"Category mismatch in {doc_path.name}: frontmatter={doc_category}, directory={category}"
                logger.warning(error)
                self.errors.append(error)
                return None

            # Build relative path from kb_path
            rel_path = str(doc_path.relative_to(self.kb_path))

            # Create index entry
            index_entry = {
                "id": doc_id,
                "category": doc_category,
                "title": metadata.get("title", ""),
                "description": metadata.get("description", ""),
                "tags": metadata.get("tags", []),
                "path": rel_path,
            }

            self._index["documents"].append(index_entry)
            self.loaded_count += 1
            logger.info(f"Loaded document: {doc_id}")
            return index_entry

        except OSError as e:
            error = f"Failed to read {doc_path.name}: {e}"
            logger.error(error)
            self.errors.append(error)
            return None
        except yaml.YAMLError as e:
            error = f"Invalid YAML in {doc_path.name}: {e}"
            logger.error(error)
            self.errors.append(error)
            return None
        except (KeyError, TypeError, ValueError) as e:
            error = f"Malformed document {doc_path.name}: {e}"
            logger.error(error)
            self.errors.append(error)
            return None

    def _validate_document_metadata(
        self, metadata: dict[str, Any] | None, filename: str
    ) -> bool:
        """Validate document metadata has all required fields, correct types, and lengths.

        Args:
            metadata: Metadata dictionary.
            filename: Original filename for error messages.

        Returns:
            True if valid, False otherwise.
        """
        if metadata is None or not isinstance(metadata, dict):
            error = f"Metadata is None or not a dict in {filename}"
            logger.warning(error)
            self.errors.append(error)
            return False

        required_fields = [
            "id",
            "category",
            "title",
            "description",
            "tags",
            "created_at",
            "updated_at",
        ]

        for field in required_fields:
            if field not in metadata:
                error = f"Missing required field '{field}' in {filename}"
                logger.warning(error)
                self.errors.append(error)
                return False

        # FIX #6: Validate string fields have correct type and length
        STRING_FIELDS = ["id", "category", "title", "description"]
        MAX_STR_LEN = 512

        for field in STRING_FIELDS:
            val = metadata.get(field)
            if not isinstance(val, str):
                error = f"Field '{field}' must be string in {filename}"
                logger.warning(error)
                self.errors.append(error)
                return False

            if not val or len(val) > MAX_STR_LEN:
                error = f"Field '{field}' must be non-empty, ≤{MAX_STR_LEN} chars in {filename}"
                logger.warning(error)
                self.errors.append(error)
                return False

        # Validate tags is list of strings
        tags = metadata.get("tags", [])
        if not isinstance(tags, list):
            error = f"Field 'tags' must be list in {filename}"
            logger.warning(error)
            self.errors.append(error)
            return False

        for tag in tags:
            if not isinstance(tag, str) or not tag or len(tag) > 64:
                error = f"Invalid tag in {filename}"
                logger.warning(error)
                self.errors.append(error)
                return False

        return True

    def _document_exists(self, doc_id: str) -> bool:
        """Check if document ID already exists in index.

        Args:
            doc_id: Document ID to check.

        Returns:
            True if document exists, False otherwise.
        """
        for doc in self._index.get("documents", []):
            if doc.get("id") == doc_id:
                return True
        return False

    def update_category_counts(self) -> None:
        """Update document counts for each category in index."""
        category_counts: dict[str, int] = {}
        for doc in self._index.get("documents", []):
            category = doc.get("category", "")
            category_counts[category] = category_counts.get(category, 0) + 1

        for category in self._index.get("categories", {}):
            self._index["categories"][category]["document_count"] = category_counts.get(
                category, 0
            )

    def save_index(self) -> bool:
        """Save the index to index.json with atomic writes.

        Uses atomic write pattern: write to temp file, then rename.

        Returns:
            True if save successful, False otherwise.
        """
        try:
            # Update timestamp and counts
            self._index["last_updated"] = datetime.now(UTC).isoformat()
            self.update_category_counts()

            # Write to temporary file first
            temp_path = self.index_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self._index, f, indent=2)

            # Atomic rename
            temp_path.replace(self.index_path)
            logger.info(f"Index saved successfully: {self.index_path}")
            return True

        except OSError as e:
            # FIX #4: Clean up stale temp file on error
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            error = f"Failed to save index: {e}"
            logger.error(error)
            self.errors.append(error)
            return False

    def validate_index(self) -> bool:
        """Validate that the current index structure is valid.

        Returns:
            True if index is valid, False otherwise.
        """
        if not isinstance(self._index, dict):
            logger.error("Index is not a dictionary")
            return False

        required_keys = ["version", "documents", "categories"]
        for key in required_keys:
            if key not in self._index:
                logger.error(f"Index missing required key: {key}")
                return False

        if not isinstance(self._index.get("documents"), list):
            logger.error("Index documents is not a list")
            return False

        if not isinstance(self._index.get("categories"), dict):
            logger.error("Index categories is not a dict")
            return False

        return True

    def get_statistics(self) -> dict[str, Any]:
        """Get loading statistics.

        Returns:
            Dictionary with loaded_count, skipped_count, and error_count.
        """
        return {
            "loaded": self.loaded_count,
            "skipped": self.skipped_count,
            "errors": len(self.errors),
            "error_messages": self.errors,
        }
