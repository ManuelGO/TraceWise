"""Unit tests for citation service."""

from app.services.citation_service import (
    AnswerWithCitations,
    Citation,
    CitationSource,
)


class TestCitationTypes:
    """Tests for citation type definitions."""

    def test_citation_type_structure(self):
        """Test Citation TypedDict has all required fields."""
        citation: Citation = {
            "source_doc_id": "doc-123",
            "chunk_index": 0,
            "relevance_score": 0.95,
            "title": "Test Document",
            "confidence": 0.85,
            "chunk_text": None,
        }

        assert citation["source_doc_id"] == "doc-123"
        assert citation["chunk_index"] == 0
        assert citation["relevance_score"] == 0.95
        assert citation["title"] == "Test Document"
        assert citation["confidence"] == 0.85
        assert citation["chunk_text"] is None

    def test_citation_without_title(self):
        """Test Citation with missing title (fallback scenario)."""
        citation: Citation = {
            "source_doc_id": "doc-456",
            "chunk_index": 2,
            "relevance_score": 0.87,
            "title": None,
            "confidence": 0.78,
            "chunk_text": None,
        }

        assert citation["title"] is None
        assert citation["source_doc_id"] == "doc-456"

    def test_citation_with_chunk_text(self):
        """Test Citation with chunk text included."""
        citation: Citation = {
            "source_doc_id": "doc-789",
            "chunk_index": 1,
            "relevance_score": 0.92,
            "title": "Knowledge Base",
            "confidence": 0.88,
            "chunk_text": "This is the source text",
        }

        assert citation["chunk_text"] == "This is the source text"

    def test_citation_source_type_structure(self):
        """Test CitationSource TypedDict has all required fields."""
        source: CitationSource = {
            "extraction_id": "ext-123",
            "title": "Compliance Guide",
            "doc_type": "pdf",
            "file_path": "/storage/compliance.pdf",
        }

        assert source["extraction_id"] == "ext-123"
        assert source["title"] == "Compliance Guide"
        assert source["doc_type"] == "pdf"
        assert source["file_path"] == "/storage/compliance.pdf"

    def test_answer_with_citations_structure(self):
        """Test AnswerWithCitations TypedDict has all required fields."""
        answer: AnswerWithCitations = {
            "answer": "The answer text",
            "tokens": {"input": 100, "output": 50, "total": 150},
            "cost": 0.0015,
            "model": "openai/gpt-4o-mini",
            "citations": [
                {
                    "source_doc_id": "doc-1",
                    "chunk_index": 0,
                    "relevance_score": 0.95,
                    "title": "Doc 1",
                    "confidence": 0.90,
                    "chunk_text": None,
                }
            ],
        }

        assert answer["answer"] == "The answer text"
        assert answer["tokens"]["total"] == 150
        assert answer["cost"] == 0.0015
        assert answer["model"] == "openai/gpt-4o-mini"
        assert len(answer["citations"]) == 1
        assert answer["citations"][0]["source_doc_id"] == "doc-1"

    def test_answer_with_empty_citations(self):
        """Test AnswerWithCitations with no citations."""
        answer: AnswerWithCitations = {
            "answer": "Answer without citations",
            "tokens": {"input": 50, "output": 25, "total": 75},
            "cost": 0.00075,
            "model": "openai/gpt-4o-mini",
            "citations": [],
        }

        assert len(answer["citations"]) == 0
        assert answer["answer"] == "Answer without citations"

    def test_answer_with_multiple_citations(self):
        """Test AnswerWithCitations with multiple citations."""
        answer: AnswerWithCitations = {
            "answer": "Multi-source answer",
            "tokens": {"input": 100, "output": 50, "total": 150},
            "cost": 0.0015,
            "model": "openai/gpt-4o-mini",
            "citations": [
                {
                    "source_doc_id": "doc-1",
                    "chunk_index": 0,
                    "relevance_score": 0.95,
                    "title": "Doc 1",
                    "confidence": 0.90,
                    "chunk_text": None,
                },
                {
                    "source_doc_id": "doc-2",
                    "chunk_index": 1,
                    "relevance_score": 0.87,
                    "title": "Doc 2",
                    "confidence": 0.82,
                    "chunk_text": None,
                },
                {
                    "source_doc_id": "doc-3",
                    "chunk_index": 2,
                    "relevance_score": 0.79,
                    "title": None,
                    "confidence": 0.75,
                    "chunk_text": None,
                },
            ],
        }

        assert len(answer["citations"]) == 3
        assert answer["citations"][0]["relevance_score"] == 0.95
        assert answer["citations"][1]["title"] == "Doc 2"
        assert answer["citations"][2]["title"] is None

    def test_citation_relevance_score_range(self):
        """Test citation relevance scores are in valid range."""
        citation: Citation = {
            "source_doc_id": "doc-min",
            "chunk_index": 0,
            "relevance_score": 0.0,
            "title": None,
            "confidence": 0.0,
            "chunk_text": None,
        }
        assert 0.0 <= citation["relevance_score"] <= 1.0

        citation_max: Citation = {
            "source_doc_id": "doc-max",
            "chunk_index": 0,
            "relevance_score": 1.0,
            "title": None,
            "confidence": 1.0,
            "chunk_text": None,
        }
        assert 0.0 <= citation_max["relevance_score"] <= 1.0

    def test_citation_confidence_range(self):
        """Test citation confidence scores are in valid range."""
        citation: Citation = {
            "source_doc_id": "doc-conf",
            "chunk_index": 0,
            "relevance_score": 0.85,
            "title": "Test",
            "confidence": 0.5,
            "chunk_text": None,
        }
        assert 0.0 <= citation["confidence"] <= 1.0

    def test_citation_chunk_index_non_negative(self):
        """Test citation chunk index is non-negative."""
        citation: Citation = {
            "source_doc_id": "doc-idx",
            "chunk_index": 0,
            "relevance_score": 0.90,
            "title": None,
            "confidence": 0.85,
            "chunk_text": None,
        }
        assert citation["chunk_index"] >= 0
