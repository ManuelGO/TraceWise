"""Unit tests for vector store service."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.models.vector_embedding import EmbeddingData, VectorEmbedding
from app.services.vector_store import (
    PostgresVectorStore,
    VectorSearchError,
    VectorStoreError,
)


class TestVectorEmbeddingModel:
    """Tests for VectorEmbedding ORM model."""

    def test_model_creation_with_all_fields(self):
        """Test creating VectorEmbedding with all fields."""
        extraction_id = uuid4()
        embedding_vec = [0.1] * 1536

        vec_embedding = VectorEmbedding(
            document_extraction_id=extraction_id,
            chunk_index=0,
            embedding=embedding_vec,
            embedding_model="openai/text-embedding-3-small",
            embedding_dim=1536,
            chunk_text="sample chunk text",
        )

        assert vec_embedding.document_extraction_id == extraction_id
        assert vec_embedding.chunk_index == 0
        assert vec_embedding.embedding == embedding_vec
        assert vec_embedding.embedding_model == "openai/text-embedding-3-small"
        assert vec_embedding.embedding_dim == 1536
        assert vec_embedding.chunk_text == "sample chunk text"
        assert vec_embedding.deleted_at is None

    def test_model_repr(self):
        """Test VectorEmbedding __repr__."""
        extraction_id = uuid4()
        embedding_vec = [0.1] * 1536

        vec_embedding = VectorEmbedding(
            document_extraction_id=extraction_id,
            chunk_index=5,
            embedding=embedding_vec,
            embedding_model="openai/text-embedding-3-small",
            embedding_dim=1536,
            chunk_text="test",
        )

        repr_str = repr(vec_embedding)
        assert "VectorEmbedding" in repr_str
        assert "chunk_index=5" in repr_str
        assert "embedding_dim=1536" in repr_str


class TestEmbeddingDataTypedDict:
    """Tests for EmbeddingData TypedDict."""

    def test_embedding_data_structure(self):
        """Test EmbeddingData TypedDict structure."""
        extraction_id = str(uuid4())
        embedding_data: EmbeddingData = {
            "document_extraction_id": extraction_id,
            "chunk_index": 0,
            "embedding": [0.1] * 1536,
            "embedding_model": "openai/text-embedding-3-small",
            "embedding_dim": 1536,
            "chunk_text": "sample text",
        }

        assert embedding_data["document_extraction_id"] == extraction_id
        assert embedding_data["chunk_index"] == 0
        assert len(embedding_data["embedding"]) == 1536
        assert embedding_data["embedding_model"] == "openai/text-embedding-3-small"
        assert embedding_data["embedding_dim"] == 1536
        assert embedding_data["chunk_text"] == "sample text"


class TestPostgresVectorStoreErrors:
    """Tests for PostgreSQL vector store error handling."""

    @pytest.fixture
    def store(self, mock_session_factory):
        """Create a VectorStore instance for testing."""
        return PostgresVectorStore(mock_session_factory)

    @pytest.mark.asyncio
    async def test_search_with_empty_vector_raises_error(self, store):
        """Test that search with empty vector raises VectorSearchError."""
        with pytest.raises(VectorSearchError, match="Query vector cannot be empty"):
            await store.search(query_vector=[], k=5)

    @pytest.mark.asyncio
    async def test_search_with_wrong_dimension_raises_error(self, store):
        """Test that search with wrong dimension raises VectorSearchError."""
        wrong_dim_vector = [0.1] * 768  # Wrong dimension

        with pytest.raises(VectorSearchError, match="dimension"):
            await store.search(query_vector=wrong_dim_vector, k=5)

    @pytest.mark.asyncio
    async def test_search_with_k_zero_returns_empty(self, store):
        """Test that search with k=0 returns empty list."""
        query_vector = [0.1] * 1536

        result = await store.search(query_vector=query_vector, k=0)
        assert result == []


class TestVectorStoreExceptions:
    """Tests for exception classes."""

    def test_vector_store_error_inheritance(self):
        """Test that VectorStoreError is an Exception."""
        error = VectorStoreError("test error")
        assert isinstance(error, Exception)

    def test_vector_search_error_inheritance(self):
        """Test that VectorSearchError inherits from VectorStoreError."""
        error = VectorSearchError("test search error")
        assert isinstance(error, VectorStoreError)

    def test_error_message_preserved(self):
        """Test that error messages are preserved."""
        message = "test error message"
        error = VectorStoreError(message)
        assert str(error) == message


# Fixtures for mocking
@pytest.fixture
def mock_session_factory():
    """Fixture providing a mocked AsyncSession factory."""
    return MagicMock()
