"""Citation and source tracking service for RAG-generated answers.

This module provides citation tracking for answers generated from retrieved context:
1. Citation type definitions: Structured citation data with metadata
2. Response schemas: TypedDict definitions for answer with citations
3. Citation mapping: Heuristic term-overlap matching to source documents
4. Citation formatting: Human-readable citation display

Citations enable users to verify answer sources and trace information back to
original documents in the knowledge base. Citations are mapped from answer text
to source documents with relevance scoring and confidence metrics.

Citation Matching Algorithm:
  1. Extract meaningful terms from answer (>3 chars, case-insensitive)
  2. For each SearchResult document:
     - Extract meaningful terms from chunk_text
     - Calculate term overlap with answer
     - If overlap >= configured threshold: include as citation
  3. Rank by relevance_score (descending)
  4. Deduplicate by source_doc_id (keep highest relevance)
  5. Return top N citations (configurable, default 5)
"""

import html
import logging
import string
from typing import TYPE_CHECKING, TypedDict

from app.config import get_settings
from app.models.vector_embedding import SearchResult

if TYPE_CHECKING:
    from app.services.llm_service import GeneratedAnswer

logger = logging.getLogger(__name__)


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


class CitationService:
    """Service for mapping answers to source citations.

    Maps generated answer text to source documents using heuristic term
    overlap matching. Provides citation deduplication, ranking, and formatting.
    """

    def __init__(self) -> None:
        """Initialize CitationService with configuration."""
        self.settings = get_settings()
        self.term_threshold = max(1, self.settings.CITATION_TERM_THRESHOLD)
        self.max_citations = self.settings.CITATION_MAX_COUNT
        self.include_chunk_text = self.settings.CITATION_INCLUDE_CHUNK_TEXT

    def map_citations(
        self, answer: str, search_results: list[SearchResult]
    ) -> list[Citation]:
        """Map answer text to source citations using term overlap.

        Extracts meaningful terms from answer and matches them against
        source documents. Returns deduplicated, ranked citations.

        Args:
            answer: Generated answer text to trace sources for
            search_results: List of SearchResult from retrieval

        Returns:
            List of Citation objects sorted by relevance (descending)
        """
        if not answer or not answer.strip():
            logger.warning("Empty answer provided to citation mapping")
            return []

        if not search_results:
            logger.info("No search results available for citation mapping")
            return []

        # Extract terms from answer
        answer_terms = self._extract_terms(answer)
        if not answer_terms:
            logger.warning("No meaningful terms extracted from answer")
            # Fallback: return all sources as citations (with low confidence)
            return self._create_fallback_citations(search_results)

        # Map each source to citation with confidence score
        mapped_citations: dict[str, Citation] = {}

        for idx, result in enumerate(search_results):
            source_id = result.get("document_extraction_id", f"source_{idx}")
            chunk_text = result.get("chunk_text", "")
            similarity_score = result.get("similarity_score", 0.0)

            # Extract terms from source chunk
            source_terms = self._extract_terms(chunk_text)

            # Calculate term overlap
            overlap = answer_terms & source_terms
            overlap_count = len(overlap)

            # Check if citation meets threshold
            if overlap_count >= self.term_threshold:
                # Jaccard similarity: overlap / union of terms
                union_terms = answer_terms | source_terms
                confidence = min(1.0, overlap_count / max(len(union_terms), 1))

                # Create or update citation (keep highest relevance per source)
                if source_id not in mapped_citations:
                    citation: Citation = {
                        "source_doc_id": source_id,
                        "chunk_index": idx,
                        "relevance_score": similarity_score,
                        "title": None,  # Title not available from SearchResult
                        "confidence": confidence,
                        "chunk_text": chunk_text if self.include_chunk_text else None,
                    }
                    mapped_citations[source_id] = citation
                else:
                    # Keep citation with higher relevance score, update all fields
                    if similarity_score > mapped_citations[source_id]["relevance_score"]:
                        mapped_citations[source_id]["relevance_score"] = similarity_score
                        mapped_citations[source_id]["chunk_index"] = idx
                        mapped_citations[source_id]["confidence"] = confidence
                        mapped_citations[source_id]["chunk_text"] = chunk_text if self.include_chunk_text else None

        # Convert to list and rank by relevance_score (descending)
        citations = list(mapped_citations.values())
        citations.sort(key=lambda c: c["relevance_score"], reverse=True)

        # Limit to max_citations
        citations = citations[: self.max_citations]

        logger.info(f"Mapped {len(citations)} citations from {len(search_results)} sources")
        return citations

    def _extract_terms(self, text: str) -> set[str]:
        """Extract meaningful terms from text.

        Meaningful terms are words > 3 characters, converted to lowercase,
        with punctuation stripped.

        Args:
            text: Text to extract terms from

        Returns:
            Set of meaningful terms
        """
        if not text:
            return set()

        words = text.lower().split()
        return {
            word.strip(string.punctuation)
            for word in words
            if len(word.strip(string.punctuation)) > 3
        }

    def _create_fallback_citations(self, search_results: list[SearchResult]) -> list[Citation]:
        """Create fallback citations when term matching doesn't find matches.

        Returns all sources as citations with low confidence (0.1), deduplicated by source_doc_id.

        Args:
            search_results: List of SearchResult to create fallback citations from

        Returns:
            List of Citation objects with low confidence
        """
        fallback_map: dict[str, Citation] = {}

        for idx, result in enumerate(search_results):
            source_id = result.get("document_extraction_id", f"source_{idx}")
            similarity_score = result.get("similarity_score", 0.0)

            if source_id not in fallback_map:
                citation: Citation = {
                    "source_doc_id": source_id,
                    "chunk_index": idx,
                    "relevance_score": similarity_score,
                    "title": None,
                    "confidence": 0.1,
                    "chunk_text": None,
                }
                fallback_map[source_id] = citation
            else:
                # Keep highest relevance score
                if similarity_score > fallback_map[source_id]["relevance_score"]:
                    fallback_map[source_id]["relevance_score"] = similarity_score
                    fallback_map[source_id]["chunk_index"] = idx

        # Rank by relevance
        citations = list(fallback_map.values())
        citations.sort(key=lambda c: c["relevance_score"], reverse=True)
        return citations[: self.max_citations]

    def format_citation(self, citation: Citation, index: int | None = None) -> str:
        """Format a single citation for display.

        Produces human-readable citation text with document metadata.
        Formats as: "[Title] (Relevance: 95%)" or fallback to "[extraction_id]".

        Args:
            citation: Citation object to format
            index: Optional index for numbered citations (e.g., [1], [2])

        Returns:
            Formatted citation string
        """
        # Get title or fallback to source_doc_id (HTML-escaped to prevent XSS)
        title = citation.get("title") or citation["source_doc_id"]
        title = html.escape(str(title))

        # Format relevance as percentage
        try:
            relevance_percent = int(citation["relevance_score"] * 100)
        except (TypeError, ValueError):
            relevance_percent = 0

        # Build base citation string
        citation_str = f"{title} (Relevance: {relevance_percent}%)"

        # Add index if provided
        if index is not None:
            citation_str = f"[{index}] {citation_str}"

        return citation_str

    def format_citations_list(self, citations: list[Citation]) -> str:
        """Format multiple citations as numbered list.

        Args:
            citations: List of Citation objects to format

        Returns:
            Formatted citations as numbered markdown list
        """
        if not citations:
            return "(No citations available)"

        lines = ["## Sources"]
        for idx, citation in enumerate(citations, 1):
            formatted = self.format_citation(citation, idx)
            lines.append(f"- {formatted}")

        return "\n".join(lines)

    def attach_citations(
        self, answer: "GeneratedAnswer", search_results: list[SearchResult]
    ) -> AnswerWithCitations:
        """Attach citations to generated answer.

        Maps answer text to source documents and creates enhanced response
        with citations. Preserves all fields from original GeneratedAnswer.

        Args:
            answer: Generated answer from LLMService
            search_results: Search results from RetrievalService

        Returns:
            Enhanced response with citations attached

        Raises:
            ValueError: If answer is not a valid GeneratedAnswer
        """
        if not isinstance(answer, dict):
            raise ValueError("Invalid GeneratedAnswer: must be a dict")

        # Validate all required GeneratedAnswer fields
        required_fields = {"answer", "tokens", "cost", "model"}
        missing_fields = required_fields - set(answer.keys())
        if missing_fields:
            raise ValueError(f"Invalid GeneratedAnswer: missing fields {missing_fields}")

        # Map citations from answer to sources
        citations = self.map_citations(answer["answer"], search_results)

        logger.info(
            f"Attached {len(citations)} citations to answer "
            f"({len(search_results)} sources available)"
        )

        # Create enhanced response with citations
        enhanced_answer: AnswerWithCitations = {
            "answer": answer["answer"],
            "tokens": answer["tokens"],
            "cost": answer["cost"],
            "model": answer["model"],
            "citations": citations,
        }

        return enhanced_answer
