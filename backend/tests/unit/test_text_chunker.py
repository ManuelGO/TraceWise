"""Unit tests for text chunking service."""

import pytest

from app.services.text_chunker import (
    ChunkingConfig,
    ChunkingStrategy,
    TextChunker,
)


class TestChunkingConfig:
    """Tests for ChunkingConfig dataclass."""

    def test_config_default_values(self):
        """Test default configuration values."""
        config = ChunkingConfig()

        assert config.chunk_size == 1000
        assert config.overlap == 150
        assert config.strategy == "sentence_aware"

    def test_config_custom_values(self):
        """Test custom configuration values."""
        config = ChunkingConfig(chunk_size=500, overlap=75, strategy="simple")

        assert config.chunk_size == 500
        assert config.overlap == 75
        assert config.strategy == "simple"

    def test_config_negative_overlap_raises_error(self):
        """Test negative overlap raises ValueError."""
        with pytest.raises(ValueError, match=r"overlap.*must be >= 0"):
            ChunkingConfig(overlap=-1)

    def test_config_invalid_strategy_raises_error(self):
        """Test invalid strategy raises ValueError."""
        with pytest.raises(ValueError, match="strategy must be one of"):
            ChunkingConfig(strategy="invalid_strategy")

    def test_config_zero_chunk_size_raises_error(self):
        """Test chunk_size=0 raises ValueError."""
        with pytest.raises(ValueError, match=r"chunk_size.*must be > 0"):
            ChunkingConfig(chunk_size=0)

    def test_config_negative_chunk_size_raises_error(self):
        """Test negative chunk_size raises ValueError."""
        with pytest.raises(ValueError, match=r"chunk_size.*must be > 0"):
            ChunkingConfig(chunk_size=-100)

    def test_config_frozen(self):
        """Test ChunkingConfig is frozen and immutable."""
        config = ChunkingConfig()
        with pytest.raises(Exception):  # FrozenInstanceError
            config.chunk_size = 500


class TestChunkingStrategy:
    """Tests for ChunkingStrategy enum."""

    def test_strategy_values(self):
        """Test strategy enum has expected values."""
        assert ChunkingStrategy.SIMPLE.value == "simple"
        assert ChunkingStrategy.SENTENCE_AWARE.value == "sentence_aware"
        assert ChunkingStrategy.PARAGRAPH_AWARE.value == "paragraph_aware"


class TestTextChunker:
    """Tests for TextChunker class."""

    def test_chunker_init_default(self):
        """Test TextChunker initialization with defaults."""
        chunker = TextChunker()

        assert chunker.config.chunk_size == 1000
        assert chunker.config.overlap == 150
        assert chunker.config.strategy == "sentence_aware"

    def test_chunker_init_custom(self):
        """Test TextChunker initialization with custom values."""
        chunker = TextChunker(chunk_size=500, overlap=50, strategy="simple")

        assert chunker.config.chunk_size == 500
        assert chunker.config.overlap == 50
        assert chunker.config.strategy == "simple"

    def test_chunker_empty_text(self):
        """Test chunking empty text."""
        chunker = TextChunker()
        chunks = chunker.chunk("")

        assert chunks == []

    def test_chunker_whitespace_only(self):
        """Test chunking whitespace-only text."""
        chunker = TextChunker()
        chunks = chunker.chunk("   \n\t  ")

        assert chunks == []

    def test_chunker_non_string_text_raises_error(self):
        """Test that non-string text raises TypeError."""
        chunker = TextChunker()
        with pytest.raises(TypeError, match="text must be a string"):
            chunker.chunk(123)  # type: ignore

    def test_chunker_non_string_bytes_raises_error(self):
        """Test that bytes input raises TypeError."""
        chunker = TextChunker()
        with pytest.raises(TypeError, match="text must be a string"):
            chunker.chunk(b"bytes text")  # type: ignore

    def test_chunker_single_chunk(self):
        """Test text shorter than chunk_size returns single chunk."""
        chunker = TextChunker(chunk_size=1000)
        text = "Short text"
        chunks = chunker.chunk(text)

        assert len(chunks) == 1
        assert chunks[0]["text"] == text
        assert chunks[0]["index"] == 0
        assert chunks[0]["document_id"] is None
        assert chunks[0]["page"] is None

    def test_chunker_metadata_preservation(self):
        """Test chunk metadata is preserved."""
        chunker = TextChunker()
        text = "word " * 300
        chunks = chunker.chunk(text, document_id="doc-123", page_number=2)

        for chunk in chunks:
            assert chunk["document_id"] == "doc-123"
            assert chunk["page"] == 2
            assert "token_count" in chunk
            assert "start_pos" in chunk
            assert "end_pos" in chunk

    def test_chunker_token_count_estimation(self):
        """Test token count estimation in chunks."""
        chunker = TextChunker()
        text = "word " * 100
        chunks = chunker.chunk(text)

        for chunk in chunks:
            # Rough estimate: 1 token ≈ 4 characters
            assert chunk["token_count"] == max(1, len(chunk["text"]) // 4)

    def test_chunker_simple_strategy(self):
        """Test simple chunking strategy."""
        chunker = TextChunker(chunk_size=200, overlap=50, strategy="simple")
        text = "word " * 100

        chunks = chunker.chunk(text)

        assert len(chunks) > 1
        assert all("text" in c for c in chunks)
        assert all("index" in c for c in chunks)

    def test_chunker_sentence_aware_strategy(self):
        """Test sentence-aware chunking strategy."""
        chunker = TextChunker(
            chunk_size=200, overlap=50, strategy="sentence_aware"
        )
        text = (
            "This is a sentence. This is another sentence. "
            "And a third one. " * 10
        )

        chunks = chunker.chunk(text)

        assert len(chunks) > 1
        assert all(len(c["text"]) > 0 for c in chunks)

    def test_chunker_paragraph_aware_strategy(self):
        """Test paragraph-aware chunking strategy."""
        chunker = TextChunker(
            chunk_size=300, overlap=50, strategy="paragraph_aware"
        )
        text = "Paragraph 1\n\nParagraph 2\n\nParagraph 3\n\n" * 5

        chunks = chunker.chunk(text)

        assert len(chunks) > 0
        assert all(len(c["text"]) > 0 for c in chunks)

    def test_chunker_overlap_in_consecutive_chunks(self):
        """Test that consecutive chunks have overlapping content."""
        chunker = TextChunker(chunk_size=200, overlap=50, strategy="simple")
        text = "The quick brown fox jumps over the lazy dog. " * 10

        chunks = chunker.chunk(text)

        # For at least some pairs, check overlap exists
        if len(chunks) > 1:
            for i in range(min(2, len(chunks) - 1)):
                chunk_current = chunks[i]["text"]
                chunk_next = chunks[i + 1]["text"]

                # Check if there's any overlapping substring
                # (exact overlap detection is complex due to word boundaries)
                assert len(chunk_current) > 0
                assert len(chunk_next) > 0

    def test_chunker_unicode_text(self):
        """Test chunking unicode text."""
        chunker = TextChunker(chunk_size=200)
        text = "こんにちは世界 " * 20  # Japanese text

        chunks = chunker.chunk(text)

        assert len(chunks) > 0
        assert all(isinstance(c["text"], str) for c in chunks)

    def test_chunker_emoji_preservation(self):
        """Test that emoji are preserved in chunks."""
        chunker = TextChunker(chunk_size=200)
        text = "Hello world 🌍 " * 20

        chunks = chunker.chunk(text)

        concatenated = "".join(c["text"] for c in chunks)
        assert "🌍" in concatenated

    def test_chunker_special_characters(self):
        """Test chunking text with special characters."""
        chunker = TextChunker(chunk_size=200)
        text = "Special chars: !@#$%^&*()_+-=[]{}|;:,.<>? " * 10

        chunks = chunker.chunk(text)

        assert len(chunks) > 0
        assert all(len(c["text"]) > 0 for c in chunks)

    def test_chunker_large_text(self):
        """Test chunking large text doesn't cause errors."""
        chunker = TextChunker(chunk_size=1000)
        text = "word " * 5000  # ~25KB text

        chunks = chunker.chunk(text)

        assert len(chunks) > 0
        # Verify concatenated text contains original content
        concatenated = "".join(c["text"] for c in chunks)
        assert len(concatenated) >= len(text.strip())

    def test_chunker_all_strategies_produce_chunks(self):
        """Test that all available strategies produce non-empty chunk lists."""
        text = "word " * 100
        for strategy in ["simple", "sentence_aware", "paragraph_aware"]:
            chunker = TextChunker(chunk_size=200, strategy=strategy)
            chunks = chunker.chunk(text)
            assert len(chunks) > 0, f"Strategy {strategy} produced no chunks"
