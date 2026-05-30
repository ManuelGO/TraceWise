"""Citation and source tracking service for RAG-generated answers.

This module provides citation tracking for answers generated from retrieved context:
1. Citation type definitions: Structured citation data with metadata
2. Response schemas: TypedDict definitions for answer with citations
3. Citation model validation: Type-safe citation handling

Citations enable users to verify answer sources and trace information back to
original documents in the knowledge base. Citations are mapped from answer text
to source documents with relevance scoring and confidence metrics.
"""

from typing import TypedDict


class Citation(TypedDict):
    """Citation reference to a source document.

    Attributes:
        source_doc_id: Extraction ID of the source document (UUID string)
        chunk_index: Index in the search results list
        relevance_score: Similarity score from vector search (0.0-1.0)
        title: Document title or name (optional, fallback to ID if missing)
        confidence: Algorithm confidence that this source was used (0.0-1.0)
        chunk_text: Source chunk text for verification (optional, controlled by config)
    """

    source_doc_id: str
    chunk_index: int
    relevance_score: float
    title: str | None
    confidence: float
    chunk_text: str | None


class CitationSource(TypedDict):
    """Source document metadata for citation display.

    Attributes:
        extraction_id: UUID of the document extraction
        title: Human-readable document title
        doc_type: Type of document (pdf, docx, xlsx, etc.)
        file_path: Original file path in storage
    """

    extraction_id: str
    title: str
    doc_type: str
    file_path: str


class AnswerWithCitations(TypedDict):
    """Answer response with source citations.

    Extends GeneratedAnswer with citations list. All fields from
    GeneratedAnswer are preserved for backward compatibility.

    Attributes:
        answer: Generated answer text from LLM
        tokens: Token usage dict with 'input', 'output', 'total'
        cost: Estimated cost in USD
        model: Model name used for generation
        citations: List of Citation objects referencing sources
    """

    answer: str
    tokens: dict[str, int]
    cost: float
    model: str
    citations: list[Citation]
