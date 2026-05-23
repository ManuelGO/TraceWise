"""Text chunking service with semantic overlap."""

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class ChunkingStrategy(StrEnum):
    """Available chunking strategies."""

    SIMPLE = "simple"
    SENTENCE_AWARE = "sentence_aware"
    PARAGRAPH_AWARE = "paragraph_aware"


@dataclass(frozen=True)
class ChunkingConfig:
    """Configuration for text chunking."""

    chunk_size: int = 1000
    overlap: int = 150
    strategy: str = "sentence_aware"

    def __post_init__(self) -> None:
        """Validate configuration parameters."""
        if self.chunk_size <= 0:
            raise ValueError(f"chunk_size ({self.chunk_size}) must be > 0")
        if self.overlap < 0:
            raise ValueError(f"overlap ({self.overlap}) must be >= 0")
        if self.strategy not in [s.value for s in ChunkingStrategy]:
            raise ValueError(
                f"strategy must be one of {[s.value for s in ChunkingStrategy]}"
            )


class TextChunker:
    """Service for chunking text with configurable overlap and strategies."""

    def __init__(
        self,
        chunk_size: int = 1000,
        overlap: int = 150,
        strategy: str = "sentence_aware",
    ) -> None:
        """Initialize TextChunker with configuration.

        Args:
            chunk_size: Target characters per chunk (default 1000)
            overlap: Overlap between consecutive chunks (default 150)
            strategy: Chunking strategy ('simple', 'sentence_aware', 'paragraph_aware')

        Raises:
            ValueError: If parameters are invalid
        """
        self.config = ChunkingConfig(
            chunk_size=chunk_size, overlap=overlap, strategy=strategy
        )

    def chunk(
        self,
        text: str,
        document_id: str | None = None,
        page_number: int | None = None,
    ) -> list[dict[str, Any]]:
        """Chunk text into overlapping segments with metadata.

        Args:
            text: Text to chunk
            document_id: Optional document identifier
            page_number: Optional page number for multi-page documents

        Returns:
            List of chunk dicts with text, index, metadata

        Raises:
            TypeError: If text is not a string
        """
        if not isinstance(text, str):
            raise TypeError(f"text must be a string, not {type(text).__name__}")

        if not text or not text.strip():
            return []

        if len(text) <= self.config.chunk_size:
            token_count = max(1, len(text) // 4)
            return [
                {
                    "text": text,
                    "index": 0,
                    "document_id": document_id,
                    "page": page_number,
                    "token_count": token_count,
                    "start_pos": 0,
                    "end_pos": len(text),
                }
            ]

        if self.config.strategy == "simple":
            return self._chunk_simple(text, document_id, page_number)
        elif self.config.strategy == "sentence_aware":
            return self._chunk_sentence_aware(text, document_id, page_number)
        elif self.config.strategy == "paragraph_aware":
            return self._chunk_paragraph_aware(text, document_id, page_number)
        else:
            # Fallback to simple
            return self._chunk_simple(text, document_id, page_number)

    def _chunk_simple(
        self,
        text: str,
        document_id: str | None = None,
        page_number: int | None = None,
    ) -> list[dict[str, Any]]:
        """Simple character-based chunking with word boundary respect."""
        chunks = []
        index = 0
        start = 0

        while start < len(text):
            end = min(start + self.config.chunk_size, len(text))

            # Try to find word boundary
            if end < len(text):
                last_space = text.rfind(" ", start, end)
                if last_space > start + self.config.chunk_size // 2:
                    end = last_space + 1

            chunk_str = text[start:end].strip()

            if chunk_str:
                token_count = max(1, len(chunk_str) // 4)
                chunks.append(
                    {
                        "text": chunk_str,
                        "index": index,
                        "document_id": document_id,
                        "page": page_number,
                        "token_count": token_count,
                        "start_pos": start,
                        "end_pos": end,
                    }
                )
                index += 1

            if end >= len(text):
                break

            step = max(1, self.config.chunk_size - self.config.overlap)
            start = start + step

        return chunks

    def _chunk_sentence_aware(
        self,
        text: str,
        document_id: str | None = None,
        page_number: int | None = None,
    ) -> list[dict[str, Any]]:
        """Sentence-aware chunking that respects sentence boundaries."""
        chunks = []
        index = 0
        start = 0

        while start < len(text):
            # Find the target end position
            end = min(start + self.config.chunk_size, len(text))

            # Try to find a sentence boundary near the target end
            if end < len(text):
                # Look for sentence-ending punctuation within reasonable range
                sentence_boundary = self._find_sentence_boundary(text, start, end)
                if sentence_boundary > start + self.config.chunk_size // 2:
                    end = sentence_boundary
                else:
                    # Fall back to word boundary
                    last_space = text.rfind(" ", start, end)
                    if last_space > start + self.config.chunk_size // 2:
                        end = last_space + 1

            chunk_str = text[start:end].strip()

            if chunk_str:
                token_count = max(1, len(chunk_str) // 4)
                chunks.append(
                    {
                        "text": chunk_str,
                        "index": index,
                        "document_id": document_id,
                        "page": page_number,
                        "token_count": token_count,
                        "start_pos": start,
                        "end_pos": end,
                    }
                )
                index += 1

            if end >= len(text):
                break

            step = max(1, self.config.chunk_size - self.config.overlap)
            start = start + step

        return chunks

    def _find_sentence_boundary(self, text: str, start: int, end: int) -> int:
        """Find the nearest sentence boundary (., ?, !) before end position.

        Args:
            text: Full text
            start: Search start position
            end: Search end position

        Returns:
            Position after sentence-ending punctuation, or start if not found
        """
        # Search backward from end for sentence-ending punctuation
        for pos in range(end - 1, start - 1, -1):
            if pos >= 0 and pos < len(text):
                if text[pos] in ".!?":
                    # Skip any following whitespace and quote marks
                    next_pos = pos + 1
                    while (
                        next_pos < len(text)
                        and text[next_pos] in ' \t\n"\')'
                    ):
                        next_pos += 1
                    return min(next_pos, end) if next_pos > pos else pos + 1
        return start

    def _chunk_paragraph_aware(
        self,
        text: str,
        document_id: str | None = None,
        page_number: int | None = None,
    ) -> list[dict[str, Any]]:
        """Paragraph-aware chunking that preserves paragraph structure."""
        # Split by paragraphs first (double newline)
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = ""
        index = 0
        start_pos = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            para_with_sep = para + "\n\n"
            proposed_chunk = (
                current_chunk + para_with_sep
                if current_chunk
                else para_with_sep
            )

            # If proposed chunk exceeds size limit, handle it
            if len(proposed_chunk) > self.config.chunk_size:
                # Emit current accumulation if any
                if current_chunk:
                    token_count = max(1, len(current_chunk) // 4)
                    chunks.append(
                        {
                            "text": current_chunk.strip(),
                            "index": index,
                            "document_id": document_id,
                            "page": page_number,
                            "token_count": token_count,
                            "start_pos": start_pos,
                            "end_pos": start_pos + len(current_chunk),
                        }
                    )
                    index += 1
                    start_pos += len(current_chunk)

                # Now handle this paragraph
                if len(para) <= self.config.chunk_size:
                    # Paragraph fits, start new chunk with it
                    current_chunk = para
                else:
                    # Paragraph is too large, use sentence-aware chunking on it
                    para_chunks = self._chunk_sentence_aware(
                        para, document_id, page_number
                    )
                    for pc in para_chunks:
                        pc["index"] = index
                        pc["start_pos"] += start_pos
                        pc["end_pos"] += start_pos
                        index += 1
                    chunks.extend(para_chunks)
                    current_chunk = ""
                    start_pos += len(para)
            else:
                # Add paragraph to current chunk
                current_chunk = (
                    current_chunk + para_with_sep if current_chunk else para
                )

        # Finalize last chunk
        if current_chunk:
            token_count = max(1, len(current_chunk) // 4)
            chunks.append(
                {
                    "text": current_chunk.strip(),
                    "index": index,
                    "document_id": document_id,
                    "page": page_number,
                    "token_count": token_count,
                    "start_pos": start_pos,
                    "end_pos": start_pos + len(current_chunk),
                }
            )

        return chunks if chunks else []


__all__ = [
    "ChunkingConfig",
    "ChunkingStrategy",
    "TextChunker",
]
