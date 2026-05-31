"""Unit tests for citation service."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.citation_service import (
    Citation,
    CitationService,
)


@pytest.fixture
def mock_settings():
    """Fixture providing mock settings for citation service tests."""
    settings = MagicMock()
    settings.CITATION_TERM_THRESHOLD = 2
    settings.CITATION_MAX_COUNT = 5
    settings.CITATION_INCLUDE_CHUNK_TEXT = False
    return settings


@pytest.fixture
def citation_service(mock_settings):
    """Fixture providing CitationService with mocked settings."""
    with patch("app.services.citation_service.get_settings", return_value=mock_settings):
        return CitationService()




class TestCitationMapping:
    """Tests for citation mapping functionality."""

    def test_map_citations_single_document(self, citation_service):
        """Test citation mapping with single matching document."""
        answer = "The compliance framework requires documentation"
        search_results = [
            {
                "embedding_id": "e-1",
                "document_extraction_id": "doc-1",
                "chunk_index": 0,
                "chunk_text": "Compliance and documentation are key requirements for the framework",
                "similarity_score": 0.95,
                "embedding_model": "openai/text-embedding-3-small",
            }
        ]

        citations = citation_service.map_citations(answer, search_results)

        assert len(citations) == 1
        assert citations[0]["source_doc_id"] == "doc-1"
        assert citations[0]["relevance_score"] == 0.95
        assert citations[0]["chunk_index"] == 0

    def test_map_citations_multiple_documents(self, citation_service):
        """Test citation mapping with multiple matching documents."""
        answer = "Security policies and access control are important"
        search_results = [
            {
                "embedding_id": "e-1",
                "document_extraction_id": "doc-1",
                "chunk_index": 0,
                "chunk_text": "Security policies define access control requirements",
                "similarity_score": 0.93,
                "embedding_model": "openai/text-embedding-3-small",
            },
            {
                "embedding_id": "e-2",
                "document_extraction_id": "doc-2",
                "chunk_index": 1,
                "chunk_text": "Access control is critical for data protection",
                "similarity_score": 0.85,
                "embedding_model": "openai/text-embedding-3-small",
            },
            {
                "embedding_id": "e-3",
                "document_extraction_id": "doc-3",
                "chunk_index": 2,
                "chunk_text": "Unrelated content about other topics",
                "similarity_score": 0.5,
                "embedding_model": "openai/text-embedding-3-small",
            },
        ]

        citations = citation_service.map_citations(answer, search_results)

        assert len(citations) == 2
        # Check ranking (highest relevance first)
        assert citations[0]["relevance_score"] == 0.93
        assert citations[1]["relevance_score"] == 0.85

    def test_map_citations_deduplication(self, citation_service, mock_settings):
        """Test that duplicate sources are deduplicated."""
        mock_settings.CITATION_TERM_THRESHOLD = 1
        # Recreate service with updated settings
        with patch("app.services.citation_service.get_settings", return_value=mock_settings):
            service = CitationService()

        answer = "Security is important"
        search_results = [
            {
                "embedding_id": "e-1",
                "document_extraction_id": "doc-1",
                "chunk_index": 0,
                "chunk_text": "Security policy first mention",
                "similarity_score": 0.90,
                "embedding_model": "openai/text-embedding-3-small",
            },
            {
                "embedding_id": "e-2",
                "document_extraction_id": "doc-1",
                "chunk_index": 1,
                "chunk_text": "Security rules second mention",
                "similarity_score": 0.85,
                "embedding_model": "openai/text-embedding-3-small",
            },
        ]

        citations = service.map_citations(answer, search_results)

        # Should have only one citation for doc-1
        assert len(citations) == 1
        assert citations[0]["source_doc_id"] == "doc-1"
        # Should keep highest relevance
        assert citations[0]["relevance_score"] == 0.90

    def test_map_citations_ranking(self, citation_service, mock_settings):
        """Test that citations are ranked by relevance score."""
        mock_settings.CITATION_TERM_THRESHOLD = 1
        with patch("app.services.citation_service.get_settings", return_value=mock_settings):
            service = CitationService()

        answer = "System requirements and installation"
        search_results = [
            {
                "embedding_id": "e-1",
                "document_extraction_id": "doc-1",
                "chunk_index": 0,
                "chunk_text": "System requirements",
                "similarity_score": 0.70,
                "embedding_model": "openai/text-embedding-3-small",
            },
            {
                "embedding_id": "e-2",
                "document_extraction_id": "doc-2",
                "chunk_index": 1,
                "chunk_text": "Installation instructions",
                "similarity_score": 0.95,
                "embedding_model": "openai/text-embedding-3-small",
            },
            {
                "embedding_id": "e-3",
                "document_extraction_id": "doc-3",
                "chunk_index": 2,
                "chunk_text": "System and installation guide",
                "similarity_score": 0.80,
                "embedding_model": "openai/text-embedding-3-small",
            },
        ]

        citations = service.map_citations(answer, search_results)

        # Should be ranked by relevance (descending)
        assert citations[0]["relevance_score"] == 0.95
        assert citations[1]["relevance_score"] == 0.80
        assert citations[2]["relevance_score"] == 0.70

    def test_map_citations_empty_answer(self, citation_service):
        """Test citation mapping with empty answer."""
        citations = citation_service.map_citations("", [])

        assert len(citations) == 0

    def test_map_citations_empty_sources(self, citation_service):
        """Test citation mapping with no search results."""
        answer = "Some answer text"
        citations = citation_service.map_citations(answer, [])

        assert len(citations) == 0

    def test_map_citations_max_limit(self, citation_service, mock_settings):
        """Test that citation count is limited to CITATION_MAX_COUNT."""
        mock_settings.CITATION_TERM_THRESHOLD = 1
        mock_settings.CITATION_MAX_COUNT = 2
        with patch("app.services.citation_service.get_settings", return_value=mock_settings):
            service = CitationService()

        answer = "Important information"
        search_results = [
            {
                "embedding_id": f"e-{i}",
                "document_extraction_id": f"doc-{i}",
                "chunk_index": i,
                "chunk_text": "Important details",
                "similarity_score": 0.90 - (i * 0.05),
                "embedding_model": "openai/text-embedding-3-small",
            }
            for i in range(5)
        ]

        citations = service.map_citations(answer, search_results)

        # Should be limited to 2
        assert len(citations) == 2

    def test_map_citations_confidence_calculation(self, citation_service):
        """Test that citation confidence is calculated correctly."""
        answer = "System security framework"
        search_results = [
            {
                "embedding_id": "e-1",
                "document_extraction_id": "doc-1",
                "chunk_index": 0,
                "chunk_text": "System and security policy framework",
                "similarity_score": 0.95,
                "embedding_model": "openai/text-embedding-3-small",
            }
        ]

        citations = citation_service.map_citations(answer, search_results)

        assert len(citations) == 1
        # Confidence should reflect term overlap
        assert 0.0 <= citations[0]["confidence"] <= 1.0

    def test_extract_terms(self, citation_service):
        """Test term extraction from text."""
        text = "This is a test with various words, punctuation! And numbers123."
        terms = citation_service._extract_terms(text)

        # Should extract words > 3 chars, lowercase, no punctuation
        assert "this" in terms  # 4 chars
        assert "test" in terms  # 4 chars
        assert "various" in terms  # 7 chars
        assert "words" in terms  # 5 chars
        assert "with" in terms  # 4 chars
        assert "numbers123" in terms  # 10 chars (digits included)
        assert "punctuation" in terms  # 11 chars
        assert "and" not in terms  # 3 chars, too short
        assert "is" not in terms  # 2 chars, too short

    def test_extract_terms_empty_text(self, citation_service):
        """Test term extraction with empty text."""
        terms = citation_service._extract_terms("")

        assert len(terms) == 0


class TestCitationFormatting:
    """Tests for citation formatting functionality."""

    def test_format_citation_with_title(self, citation_service):
        """Test formatting citation with title."""
        citation: Citation = {
            "source_doc_id": "doc-1",
            "chunk_index": 0,
            "relevance_score": 0.95,
            "title": "Compliance Guide",
            "confidence": 0.85,
            "chunk_text": None,
        }

        formatted = citation_service.format_citation(citation)

        assert "Compliance Guide" in formatted
        assert "95%" in formatted

    def test_format_citation_without_title(self, citation_service):
        """Test formatting citation without title (fallback to ID)."""
        citation: Citation = {
            "source_doc_id": "doc-xyz-123",
            "chunk_index": 2,
            "relevance_score": 0.87,
            "title": None,
            "confidence": 0.80,
            "chunk_text": None,
        }

        formatted = citation_service.format_citation(citation)

        assert "doc-xyz-123" in formatted
        assert "87%" in formatted

    def test_format_citation_with_index(self, citation_service):
        """Test formatting citation with index."""
        citation: Citation = {
            "source_doc_id": "doc-1",
            "chunk_index": 0,
            "relevance_score": 0.90,
            "title": "Document",
            "confidence": 0.85,
            "chunk_text": None,
        }

        formatted = citation_service.format_citation(citation, index=1)

        assert "[1]" in formatted
        assert "Document" in formatted

    def test_format_citations_list_multiple(self, citation_service):
        """Test formatting multiple citations as list."""
        citations: list[Citation] = [
            {
                "source_doc_id": "doc-1",
                "chunk_index": 0,
                "relevance_score": 0.95,
                "title": "Doc One",
                "confidence": 0.90,
                "chunk_text": None,
            },
            {
                "source_doc_id": "doc-2",
                "chunk_index": 1,
                "relevance_score": 0.85,
                "title": "Doc Two",
                "confidence": 0.80,
                "chunk_text": None,
            },
        ]

        formatted = citation_service.format_citations_list(citations)

        assert "## Sources" in formatted
        assert "[1]" in formatted
        assert "[2]" in formatted
        assert "Doc One" in formatted
        assert "Doc Two" in formatted

    def test_format_citations_list_empty(self, citation_service):
        """Test formatting empty citations list."""
        formatted = citation_service.format_citations_list([])

        assert "No citations available" in formatted

    def test_format_citation_relevance_rounding(self, citation_service):
        """Test that relevance is rounded correctly."""
        citation: Citation = {
            "source_doc_id": "doc-1",
            "chunk_index": 0,
            "relevance_score": 0.876,
            "title": "Document",
            "confidence": 0.85,
            "chunk_text": None,
        }

        formatted = citation_service.format_citation(citation)

        # 0.876 * 100 = 87.6, int() = 87
        assert "87%" in formatted


class TestResponseIntegration:
    """Tests for response integration with citations."""

    def test_attach_citations_end_to_end(self, citation_service):
        """Test end-to-end citation attachment to answer."""
        from app.services.llm_service import GeneratedAnswer

        answer: GeneratedAnswer = {
            "answer": "The security framework requires proper documentation",
            "tokens": {"input": 100, "output": 50, "total": 150},
            "cost": 0.0015,
            "model": "openai/gpt-4o-mini",
        }

        search_results = [
            {
                "embedding_id": "e-1",
                "document_extraction_id": "doc-1",
                "chunk_index": 0,
                "chunk_text": "Security framework and documentation guidelines",
                "similarity_score": 0.95,
                "embedding_model": "openai/text-embedding-3-small",
            },
            {
                "embedding_id": "e-2",
                "document_extraction_id": "doc-2",
                "chunk_index": 1,
                "chunk_text": "Unrelated content",
                "similarity_score": 0.5,
                "embedding_model": "openai/text-embedding-3-small",
            },
        ]

        enhanced = citation_service.attach_citations(answer, search_results)

        # Check all answer fields preserved
        assert enhanced["answer"] == answer["answer"]
        assert enhanced["tokens"] == answer["tokens"]
        assert enhanced["cost"] == answer["cost"]
        assert enhanced["model"] == answer["model"]

        # Check citations attached
        assert len(enhanced["citations"]) > 0
        assert enhanced["citations"][0]["source_doc_id"] == "doc-1"

    def test_attach_citations_preserves_fields(self, citation_service):
        """Test that all GeneratedAnswer fields are preserved."""
        from app.services.llm_service import GeneratedAnswer

        answer: GeneratedAnswer = {
            "answer": "Test answer",
            "tokens": {"input": 200, "output": 100, "total": 300},
            "cost": 0.003,
            "model": "openai/gpt-4o",
        }

        enhanced = citation_service.attach_citations(answer, [])

        assert enhanced["answer"] == "Test answer"
        assert enhanced["tokens"]["total"] == 300
        assert enhanced["cost"] == 0.003
        assert enhanced["model"] == "openai/gpt-4o"

    def test_attach_citations_invalid_answer(self, citation_service):
        """Test error handling for invalid answer."""
        invalid_answer = {"text": "Missing 'answer' field"}

        with pytest.raises(ValueError, match="Invalid GeneratedAnswer"):
            citation_service.attach_citations(invalid_answer, [])  # type: ignore

    def test_attach_citations_empty_sources(self, citation_service):
        """Test citation attachment with no search results."""
        from app.services.llm_service import GeneratedAnswer

        answer: GeneratedAnswer = {
            "answer": "Answer with no sources",
            "tokens": {"input": 50, "output": 25, "total": 75},
            "cost": 0.00075,
            "model": "openai/gpt-4o-mini",
        }

        enhanced = citation_service.attach_citations(answer, [])

        assert enhanced["answer"] == "Answer with no sources"
        assert len(enhanced["citations"]) == 0
