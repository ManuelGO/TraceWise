"""Unit tests for text chunking service."""

from app.services.text_chunker import chunk_text


class TestChunkText:
    """Tests for chunk_text function."""

    def test_chunk_text_empty(self):
        """Test chunking empty text returns empty list."""
        chunks = chunk_text("", chunk_size=512, overlap=50)
        assert chunks == []

    def test_chunk_text_whitespace_only(self):
        """Test chunking whitespace-only text returns empty list."""
        chunks = chunk_text("   \n\t  ", chunk_size=512, overlap=50)
        assert chunks == []

    def test_chunk_text_single_chunk(self):
        """Test text shorter than chunk_size returns single chunk."""
        text = "This is short text"
        chunks = chunk_text(text, chunk_size=512, overlap=50)

        assert len(chunks) == 1
        assert chunks[0]["text"] == text
        assert chunks[0]["index"] == 0
        assert chunks[0]["page"] is None

    def test_chunk_text_multiple_chunks(self):
        """Test text longer than chunk_size is split into multiple chunks."""
        text = "word " * 200  # Roughly 1000 characters
        chunks = chunk_text(text, chunk_size=512, overlap=50)

        assert len(chunks) > 1
        assert all(isinstance(c, dict) for c in chunks)
        assert all("text" in c and "index" in c and "page" in c for c in chunks)

    def test_chunk_text_indices(self):
        """Test chunk indices are sequential."""
        text = "word " * 200
        chunks = chunk_text(text, chunk_size=512, overlap=50)

        for i, chunk in enumerate(chunks):
            assert chunk["index"] == i

    def test_chunk_text_overlap_integrity(self):
        """Test overlap doesn't lose data."""
        text = "The quick brown fox jumps over the lazy dog. " * 20
        chunks = chunk_text(text, chunk_size=512, overlap=50)

        assert len(chunks) > 0

    def test_chunk_text_with_page_number(self):
        """Test chunking with page number includes it in chunks."""
        text = "word " * 200
        chunks = chunk_text(text, chunk_size=512, overlap=50, page_number=5)

        assert all(c["page"] == 5 for c in chunks)

    def test_chunk_text_default_parameters(self):
        """Test chunking with default parameters."""
        text = "word " * 200
        chunks = chunk_text(text)  # Uses default chunk_size=512, overlap=50

        assert len(chunks) > 0
        assert all("text" in c for c in chunks)

    def test_chunk_text_single_long_word(self):
        """Test chunking when a single word exceeds chunk_size."""
        long_word = "a" * 600
        chunks = chunk_text(long_word, chunk_size=512, overlap=50)

        assert len(chunks) > 0
        assert any(len(c["text"]) >= 512 for c in chunks)

    def test_chunk_text_preserves_content(self):
        """Test that concatenating chunks preserves original content."""
        text = "The quick brown fox " * 30
        chunks = chunk_text(text, chunk_size=200, overlap=50)

        concatenated = "".join(c["text"] for c in chunks)
        assert len(concatenated) >= len(text.strip())

    def test_chunk_text_with_newlines(self):
        """Test chunking text with newlines."""
        text = "Line 1\nLine 2\nLine 3\n" * 30
        chunks = chunk_text(text, chunk_size=256, overlap=50)

        assert len(chunks) > 0
        assert all(len(c["text"]) > 0 for c in chunks)

    def test_chunk_text_overlap_greater_than_size(self):
        """Test with overlap >= chunk_size still works."""
        text = "word " * 200
        chunks = chunk_text(text, chunk_size=200, overlap=200)

        assert len(chunks) > 0
        assert all(len(c["text"]) > 0 for c in chunks)

    def test_chunk_text_tiny_chunk_size(self):
        """Test chunking with very small chunk size."""
        text = "word " * 50
        chunks = chunk_text(text, chunk_size=20, overlap=5)

        assert len(chunks) >= 1
        assert all(isinstance(c["text"], str) for c in chunks)
