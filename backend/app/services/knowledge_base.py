"""Knowledge base service for retrieving and managing regulatory content."""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

MAX_DOC_SIZE = 10 * 1024 * 1024  # 10MB document size limit


@dataclass
class KBDocument:
    """Represents a knowledge base document with metadata and content."""

    id: str
    category: str
    title: str
    description: str
    tags: list[str]
    content: str
    source: str
    version: str
    related_documents: list[str]
    created_at: str
    updated_at: str


@dataclass
class CategoryInfo:
    """Information about a knowledge base category."""

    name: str
    description: str
    document_count: int


class KnowledgeBase:
    """Service for loading, retrieving, and searching knowledge base documents.

    The knowledge base is organized by category and indexed for fast lookup.
    Documents are lazy-loaded on first access and cached in memory.

    Example:
        >>> kb = KnowledgeBase('/path/to/knowledge_base')
        >>> doc = kb.get_document('eudr-001')
        >>> if doc:
        ...     print(doc.title)
        >>> all_docs = kb.list_documents()
        >>> eudr_docs = kb.list_documents(category='eudr_summaries')
    """

    def __init__(self, kb_path: str | None = None):
        """Initialize the knowledge base service.

        Args:
            kb_path: Path to knowledge base directory. If None, uses default path.

        Raises:
            FileNotFoundError: If knowledge base directory or index doesn't exist.
        """
        if kb_path is None:
            kb_path = str(Path(__file__).parent.parent / "data" / "knowledge_base")

        self.kb_path = Path(kb_path)
        if not self.kb_path.exists():
            raise FileNotFoundError(f"Knowledge base path not found: {self.kb_path}")

        self.index_path = self.kb_path / "index.json"
        if not self.index_path.exists():
            raise FileNotFoundError(f"Index file not found: {self.index_path}")

        self._index: dict[str, Any] | None = None
        self._documents_cache: dict[str, KBDocument] = {}
        self._load_index()

    def _load_index(self) -> None:
        """Load and parse the index.json file with validation.

        Raises:
            ValueError: If index.json is invalid or malformed.
        """
        try:
            with open(self.index_path, encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse index.json: {e}")
            raise ValueError(f"Invalid JSON in index.json: {e}") from e

        # Extract and validate categories (FIX #7: Category Validation)
        self._valid_categories = frozenset(data.get("categories", {}).keys())
        if not self._valid_categories:
            self._valid_categories = frozenset(
                {
                    "eudr_summaries",
                    "regulatory_guidance",
                    "documentation_requirements",
                    "risk_assessment_guidance",
                    "traceability_obligations",
                }
            )
            logger.info("Using default categories (none defined in index)")

        # Validate and load documents (FIX #3: Dict Access Guards)
        validated_docs = []
        for doc_info in data.get("documents", []):
            doc_id = doc_info.get("id")
            doc_path = doc_info.get("path")
            category = doc_info.get("category")

            if not doc_id or not doc_path or not category:
                logger.warning(
                    f"Skipping malformed index entry (missing required fields): {doc_info}"
                )
                continue

            validated_docs.append(
                {
                    "id": doc_id,
                    "path": doc_path,
                    "category": category,
                }
            )

        self._index = {
            "documents": validated_docs,
            "categories": data.get("categories", {}),
        }

        logger.info(f"Loaded knowledge base index with {len(validated_docs)} documents")

    def _load_document(self, doc_id: str) -> KBDocument | None:
        """Load a single document from disk, parsing metadata and content.

        Documents are stored as markdown files with YAML frontmatter.
        Metadata is validated before document is returned.

        Args:
            doc_id: Document ID to load.

        Returns:
            KBDocument with parsed metadata and content, or None if not found.
        """
        if not self._index:
            return None

        # Find document in index using safe access
        doc_info: dict[str, Any] | None = None
        for doc in self._index.get("documents", []):
            if doc.get("id") == doc_id:
                doc_info = doc
                break

        if not doc_info:
            logger.debug(f"Document not found in index: {doc_id}")
            return None

        # Validate required index fields
        doc_path_str = doc_info.get("path")
        if not doc_path_str:
            logger.warning(f"Index entry for {doc_id} missing 'path' field")
            return None

        # Load document file with path traversal protection
        doc_path = (self.kb_path / doc_path_str).resolve()
        kb_path_resolved = self.kb_path.resolve()

        # Verify path is within kb_path (FIX #1: Path Traversal Protection)
        try:
            doc_path.relative_to(kb_path_resolved)
        except ValueError:
            logger.warning(f"Path traversal blocked for doc {doc_id}: {doc_path_str}")
            return None

        if not doc_path.exists():
            logger.warning(f"Document file not found: {doc_path}")
            return None

        try:
            with open(doc_path, encoding="utf-8") as f:
                content = f.read()

            # Check file size
            file_size = doc_path.stat().st_size
            if file_size > MAX_DOC_SIZE:
                logger.error(f"Document {doc_id} exceeds max size: {file_size} bytes")
                return None

            # Split frontmatter and content using line-anchored delimiters
            if not content.startswith("---"):
                logger.warning(f"Document missing frontmatter: {doc_id}")
                return None

            parts = re.split(r"^---$", content, maxsplit=2, flags=re.MULTILINE)
            if len(parts) < 3:
                logger.warning(f"Invalid frontmatter in document: {doc_id}")
                return None

            frontmatter_str = parts[1].strip()
            doc_content = parts[2].strip()

            # Parse YAML frontmatter
            try:
                metadata = yaml.safe_load(frontmatter_str)
            except yaml.YAMLError as e:
                logger.error(f"YAML parsing failed for {doc_id}: {e}")
                return None

            if not self._validate_metadata(metadata):
                logger.warning(f"Invalid metadata in document: {doc_id}")
                return None

            # Create document object using index ID as authority (FIX #5)
            doc = KBDocument(
                id=doc_id,  # Use index ID, not frontmatter ID
                category=metadata.get("category", ""),
                title=metadata.get("title", ""),
                description=metadata.get("description", ""),
                tags=metadata.get("tags", []),
                content=doc_content,
                source=metadata.get("source", ""),
                version=metadata.get("version", "1.0"),
                related_documents=metadata.get("related_documents", []),
                created_at=metadata.get("created_at", ""),
                updated_at=metadata.get("updated_at", ""),
            )

            # Validate ID consistency
            if metadata.get("id") and metadata["id"] != doc_id:
                logger.warning(f"ID mismatch for {doc_id}: frontmatter has '{metadata['id']}'")

            self._documents_cache[doc_id] = doc
            return doc

        except OSError as e:
            logger.error(f"Failed to read document {doc_id}: {e}")
            return None
        except yaml.YAMLError as e:
            logger.error(f"Invalid YAML in {doc_id}: {e}")
            return None
        except (KeyError, TypeError, ValueError) as e:
            logger.error(f"Malformed document {doc_id}: {e}")
            return None

    def _validate_metadata(self, metadata: dict[str, Any] | None) -> bool:
        """Validate document metadata.

        Args:
            metadata: Metadata dictionary to validate, or None.

        Returns:
            True if valid, False otherwise.
        """
        if metadata is None or not isinstance(metadata, dict):
            logger.warning("Metadata is None or not a dict")
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
                logger.warning(f"Missing required field: {field}")
                return False

        # Validate category against index-derived list (FIX #7)
        if metadata.get("category") not in self._valid_categories:
            logger.warning(f"Invalid category: {metadata.get('category')}")
            return False

        # Validate tags is list
        if not isinstance(metadata.get("tags"), list):
            logger.warning("Tags must be a list")
            return False

        return True

    def get_document(self, doc_id: str) -> KBDocument | None:
        """Retrieve a single document by ID.

        Documents are cached in memory after first load.

        Args:
            doc_id: Document ID to retrieve.

        Returns:
            KBDocument object, or None if not found.

        Example:
            >>> kb = KnowledgeBase()
            >>> doc = kb.get_document('eudr-001')
            >>> if doc:
            ...     print(doc.title, doc.description)
        """
        # Check cache first
        if doc_id in self._documents_cache:
            return self._documents_cache[doc_id]

        # Load from disk
        return self._load_document(doc_id)

    def list_documents(self, category: str | None = None) -> list[KBDocument]:
        """List all documents, optionally filtered by category.

        Args:
            category: Optional category name to filter by. If None, returns all.

        Returns:
            List of KBDocument objects (may be empty).

        Example:
            >>> kb = KnowledgeBase()
            >>> all_docs = kb.list_documents()
            >>> eudr_docs = kb.list_documents(category='eudr_summaries')
        """
        if not self._index:
            return []

        documents = []
        for doc_info in self._index.get("documents", []):
            if category is not None and doc_info["category"] != category:
                continue

            doc = self.get_document(doc_info["id"])
            if doc:
                documents.append(doc)

        return documents

    def get_related_documents(self, doc_id: str) -> list[KBDocument]:
        """Get documents related to the specified document.

        Returns documents referenced in the source document's related_documents list.
        Missing references are silently skipped with a warning logged.

        Args:
            doc_id: Document ID to get related documents for.

        Returns:
            List of related KBDocument objects (may be empty).

        Example:
            >>> kb = KnowledgeBase()
            >>> doc = kb.get_document('eudr-001')
            >>> related = kb.get_related_documents('eudr-001')
        """
        doc = self.get_document(doc_id)
        if not doc:
            return []

        related = []
        for related_id in doc.related_documents:
            related_doc = self.get_document(related_id)
            if related_doc:
                related.append(related_doc)
            else:
                logger.warning(f"Related document not found: {related_id} (referenced by {doc_id})")

        return related

    def search_documents(self, query: str, category: str | None = None) -> list[KBDocument]:
        """Search documents by title, description, tags, and content.

        Search is case-insensitive and matches partial strings.
        Searches across title, description, tags, and document content.

        Args:
            query: Search query string (case-insensitive).
            category: Optional category to limit search to.

        Returns:
            List of matching KBDocument objects (may be empty).

        Example:
            >>> kb = KnowledgeBase()
            >>> results = kb.search_documents('due diligence')
            >>> eudr_results = kb.search_documents(
            ...     'compliance', category='eudr_summaries'
            ... )
        """
        if not query:
            return []

        if not self._index:
            return []

        query_lower = query.lower()
        results = []

        for doc_info in self._index.get("documents", []):
            if category is not None and doc_info["category"] != category:
                continue

            # Quick check in index metadata first
            doc_id = doc_info["id"]
            if self._matches_query(
                query_lower,
                doc_info.get("title", ""),
                doc_info.get("description", ""),
                doc_info.get("tags", []),
            ):
                doc = self.get_document(doc_id)
                if doc:
                    results.append(doc)
                continue

            # Load and search content if metadata didn't match
            doc = self.get_document(doc_id)
            if doc and self._matches_query_in_content(query_lower, doc.content):
                results.append(doc)

        return results

    def _matches_query(self, query: str, title: str, description: str, tags: list[str]) -> bool:
        """Check if query matches in title, description, or tags.

        Args:
            query: Lowercase query string.
            title: Document title.
            description: Document description.
            tags: List of document tags.

        Returns:
            True if query matches any field.
        """
        if query in title.lower():
            return True
        if query in description.lower():
            return True
        for tag in tags:
            if query in tag.lower():
                return True
        return False

    def _matches_query_in_content(self, query: str, content: str) -> bool:
        """Check if query matches in document content.

        Args:
            query: Lowercase query string.
            content: Document content text.

        Returns:
            True if query found in content.
        """
        return query in content.lower()

    def get_categories(self) -> dict[str, CategoryInfo]:
        """Get metadata for all knowledge base categories.

        Returns:
            Dictionary mapping category name to CategoryInfo object.

        Example:
            >>> kb = KnowledgeBase()
            >>> categories = kb.get_categories()
            >>> for name, info in categories.items():
            ...     print(f"{name}: {info.document_count} documents")
        """
        if not self._index:
            return {}

        result: dict[str, CategoryInfo] = {}
        for cat_id, cat_info in self._index.get("categories", {}).items():
            result[cat_id] = CategoryInfo(
                name=cat_info.get("name", cat_id),
                description=cat_info.get("description", ""),
                document_count=cat_info.get("document_count", 0),
            )

        return result
