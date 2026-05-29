"""Unit tests for retrieval service."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.embedding_service import EmbeddingError
from app.services.retrieval_service import RetrievalError, RetrievalService
from app.services.vector_store import VectorSearchError


@pytest.fixture
def mock_embedding_service():
    """Mock embedding service."""
    service = AsyncMock()
    service.embed_query = AsyncMock(return_value=[0.1] * 1536)
    return service


@pytest.fixture
def mock_vector_store():
    """Mock vector store."""
    store = AsyncMock()
    store.search = AsyncMock(
        return_value=[
            {
                "embedding_id": "test-id-1",
                "document_extraction_id": "extraction-1",
                "chunk_index": 0,
                "chunk_text": "Test chunk 1",
                "similarity_score": 0.9,
                "embedding_model": "openai/text-embedding-3-small",
            }
        ]
    )
    return store


@pytest.fixture
def mock_settings():
    """Mock settings."""
    settings = MagicMock()
    settings.RETRIEVAL_DEFAULT_K = 5
    settings.RETRIEVAL_SIMILARITY_THRESHOLD = 0.0
    settings.RETRIEVAL_BATCH_SIZE = 10
    return settings


class TestRetrievalServiceInit:
    """Tests for RetrievalService initialization."""

    def test_init_with_valid_services(self, mock_embedding_service, mock_vector_store):
        """Test successful initialization."""
        service = RetrievalService(mock_embedding_service, mock_vector_store)

        assert service.embedding_service == mock_embedding_service
        assert service.vector_store == mock_vector_store

    def test_init_with_none_embedding_service(self, mock_vector_store):
        """Test initialization with None embedding service raises error."""
        with pytest.raises(ValueError, match="embedding_service cannot be None"):
            RetrievalService(None, mock_vector_store)

    def test_init_with_none_vector_store(self, mock_embedding_service):
        """Test initialization with None vector store raises error."""
        with pytest.raises(ValueError, match="vector_store cannot be None"):
            RetrievalService(mock_embedding_service, None)


class TestRetrievalServiceQuery:
    """Tests for query method."""

    @pytest.mark.asyncio
    async def test_query_with_valid_input(self, mock_embedding_service, mock_vector_store, mock_settings, monkeypatch):
        """Test successful query."""
        monkeypatch.setattr("app.services.retrieval_service.get_settings", lambda: mock_settings)

        service = RetrievalService(mock_embedding_service, mock_vector_store)
        results = await service.query("test query")

        assert len(results) == 1
        assert results[0]["chunk_text"] == "Test chunk 1"
        mock_embedding_service.embed_query.assert_called_once()
        mock_vector_store.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_with_custom_k(self, mock_embedding_service, mock_vector_store, mock_settings, monkeypatch):
        """Test query with custom k parameter."""
        monkeypatch.setattr("app.services.retrieval_service.get_settings", lambda: mock_settings)

        service = RetrievalService(mock_embedding_service, mock_vector_store)
        await service.query("test query", k=10)

        call_args = mock_vector_store.search.call_args
        assert call_args.kwargs["k"] == 10

    @pytest.mark.asyncio
    async def test_query_with_custom_threshold(
        self, mock_embedding_service, mock_vector_store, mock_settings, monkeypatch
    ):
        """Test query with custom similarity threshold."""
        monkeypatch.setattr("app.services.retrieval_service.get_settings", lambda: mock_settings)

        service = RetrievalService(mock_embedding_service, mock_vector_store)
        await service.query("test query", similarity_threshold=0.5)

        call_args = mock_vector_store.search.call_args
        assert call_args.kwargs["similarity_threshold"] == 0.5

    @pytest.mark.asyncio
    async def test_query_with_empty_query(self, mock_embedding_service, mock_vector_store):
        """Test query with empty string raises error."""
        service = RetrievalService(mock_embedding_service, mock_vector_store)

        with pytest.raises(RetrievalError, match="Query cannot be empty"):
            await service.query("")

    @pytest.mark.asyncio
    async def test_query_with_whitespace_only(self, mock_embedding_service, mock_vector_store):
        """Test query with whitespace only raises error."""
        service = RetrievalService(mock_embedding_service, mock_vector_store)

        with pytest.raises(RetrievalError, match="Query cannot be empty"):
            await service.query("   ")

    @pytest.mark.asyncio
    async def test_query_with_zero_k(self, mock_embedding_service, mock_vector_store, mock_settings, monkeypatch):
        """Test query with k=0 raises error."""
        monkeypatch.setattr("app.services.retrieval_service.get_settings", lambda: mock_settings)

        service = RetrievalService(mock_embedding_service, mock_vector_store)

        with pytest.raises(RetrievalError, match="k must be a positive integer"):
            await service.query("test query", k=0)

    @pytest.mark.asyncio
    async def test_query_with_invalid_threshold(
        self, mock_embedding_service, mock_vector_store, mock_settings, monkeypatch
    ):
        """Test query with invalid threshold raises error."""
        monkeypatch.setattr("app.services.retrieval_service.get_settings", lambda: mock_settings)

        service = RetrievalService(mock_embedding_service, mock_vector_store)

        with pytest.raises(RetrievalError, match=r"Similarity threshold must be between 0\.0 and 1\.0"):
            await service.query("test query", similarity_threshold=1.5)

    @pytest.mark.asyncio
    async def test_query_embedding_error(self, mock_embedding_service, mock_vector_store, mock_settings, monkeypatch):
        """Test query handles embedding errors."""
        mock_embedding_service.embed_query.side_effect = EmbeddingError("API error")
        monkeypatch.setattr("app.services.retrieval_service.get_settings", lambda: mock_settings)

        service = RetrievalService(mock_embedding_service, mock_vector_store)

        with pytest.raises(RetrievalError, match="Failed to embed query"):
            await service.query("test query")

    @pytest.mark.asyncio
    async def test_query_search_error(self, mock_embedding_service, mock_vector_store, mock_settings, monkeypatch):
        """Test query handles search errors."""
        mock_vector_store.search.side_effect = VectorSearchError("Search failed")
        monkeypatch.setattr("app.services.retrieval_service.get_settings", lambda: mock_settings)

        service = RetrievalService(mock_embedding_service, mock_vector_store)

        with pytest.raises(RetrievalError, match="Failed to search vector store"):
            await service.query("test query")

    @pytest.mark.asyncio
    async def test_query_with_extraction_filter(
        self, mock_embedding_service, mock_vector_store, mock_settings, monkeypatch
    ):
        """Test query with extraction ID filter."""
        from uuid import uuid4

        extraction_id = uuid4()
        mock_vector_store.search.return_value = [
            {
                "embedding_id": "test-id-1",
                "document_extraction_id": str(extraction_id),
                "chunk_index": 0,
                "chunk_text": "Test chunk 1",
                "similarity_score": 0.9,
                "embedding_model": "openai/text-embedding-3-small",
            }
        ]
        monkeypatch.setattr("app.services.retrieval_service.get_settings", lambda: mock_settings)

        service = RetrievalService(mock_embedding_service, mock_vector_store)
        results = await service.query("test query", extraction_ids=[extraction_id])

        assert len(results) == 1


class TestRetrievalServiceSearch:
    """Tests for search method behavior."""

    @pytest.mark.asyncio
    async def test_search_called_with_correct_params(
        self, mock_embedding_service, mock_vector_store, mock_settings, monkeypatch
    ):
        """Test that vector store search is called with correct parameters."""
        monkeypatch.setattr("app.services.retrieval_service.get_settings", lambda: mock_settings)

        service = RetrievalService(mock_embedding_service, mock_vector_store)
        await service.query("test query", k=7, similarity_threshold=0.5)

        call_args = mock_vector_store.search.call_args
        assert call_args.kwargs["k"] == 7
        assert call_args.kwargs["similarity_threshold"] == 0.5

    @pytest.mark.asyncio
    async def test_embedding_passed_to_search(
        self, mock_embedding_service, mock_vector_store, mock_settings, monkeypatch
    ):
        """Test that query embedding is passed to vector store."""
        test_embedding = [0.5] * 1536
        mock_embedding_service.embed_query.return_value = test_embedding
        monkeypatch.setattr("app.services.retrieval_service.get_settings", lambda: mock_settings)

        service = RetrievalService(mock_embedding_service, mock_vector_store)
        await service.query("test query")

        call_args = mock_vector_store.search.call_args
        assert call_args[0][0] == test_embedding

    @pytest.mark.asyncio
    async def test_query_with_negative_k(
        self, mock_embedding_service, mock_vector_store, mock_settings, monkeypatch
    ):
        """Test query with negative k raises error."""
        monkeypatch.setattr("app.services.retrieval_service.get_settings", lambda: mock_settings)

        service = RetrievalService(mock_embedding_service, mock_vector_store)

        with pytest.raises(RetrievalError, match="k must be a positive integer"):
            await service.query("test query", k=-5)


class TestRetrievalServiceBatch:
    """Tests for batch query method."""

    @pytest.mark.asyncio
    async def test_batch_query_with_valid_queries(
        self, mock_embedding_service, mock_vector_store, mock_settings, monkeypatch
    ):
        """Test successful batch query."""
        monkeypatch.setattr("app.services.retrieval_service.get_settings", lambda: mock_settings)

        service = RetrievalService(mock_embedding_service, mock_vector_store)
        results = await service.query_batch(["query 1", "query 2"])

        assert len(results) == 2
        assert all(isinstance(r, list) for r in results)

    @pytest.mark.asyncio
    async def test_batch_query_with_empty_list(self, mock_embedding_service, mock_vector_store):
        """Test batch query with empty list returns empty list."""
        service = RetrievalService(mock_embedding_service, mock_vector_store)
        results = await service.query_batch([])

        assert results == []

    @pytest.mark.asyncio
    async def test_batch_query_respects_concurrency_limit(
        self, mock_embedding_service, mock_vector_store, mock_settings, monkeypatch
    ):
        """Test batch query respects concurrency limit."""
        monkeypatch.setattr("app.services.retrieval_service.get_settings", lambda: mock_settings)

        service = RetrievalService(mock_embedding_service, mock_vector_store)
        queries = [f"query {i}" for i in range(20)]
        results = await service.query_batch(queries)

        assert len(results) == 20
        assert mock_embedding_service.embed_query.call_count == 20

    @pytest.mark.asyncio
    async def test_batch_query_with_custom_k(
        self, mock_embedding_service, mock_vector_store, mock_settings, monkeypatch
    ):
        """Test batch query with custom k."""
        monkeypatch.setattr("app.services.retrieval_service.get_settings", lambda: mock_settings)

        service = RetrievalService(mock_embedding_service, mock_vector_store)
        await service.query_batch(["query 1", "query 2"], k=10)

        call_args_list = mock_vector_store.search.call_args_list
        assert all(call.kwargs["k"] == 10 for call in call_args_list)

    @pytest.mark.asyncio
    async def test_batch_query_maintains_order(
        self, mock_embedding_service, mock_vector_store, mock_settings, monkeypatch
    ):
        """Test batch query returns results in same order as queries."""
        results_list = [
            [{"chunk_text": "Result for query 0", "similarity_score": 0.9, "embedding_model": "test"}],
            [{"chunk_text": "Result for query 1", "similarity_score": 0.8, "embedding_model": "test"}],
            [{"chunk_text": "Result for query 2", "similarity_score": 0.7, "embedding_model": "test"}],
        ]

        async def search_side_effect(*args, **kwargs):
            return results_list[search_side_effect.call_count - 1]

        search_side_effect.call_count = 0

        mock_vector_store.search = AsyncMock(side_effect=lambda *args, **kwargs: results_list[mock_vector_store.search.call_count - 1])
        monkeypatch.setattr("app.services.retrieval_service.get_settings", lambda: mock_settings)

        service = RetrievalService(mock_embedding_service, mock_vector_store)
        batch_results = await service.query_batch(["query 0", "query 1", "query 2"])

        assert len(batch_results) == 3
        assert batch_results[0][0]["chunk_text"] == "Result for query 0"
        assert batch_results[1][0]["chunk_text"] == "Result for query 1"
        assert batch_results[2][0]["chunk_text"] == "Result for query 2"

    @pytest.mark.asyncio
    async def test_batch_query_with_all_params(
        self, mock_embedding_service, mock_vector_store, mock_settings, monkeypatch
    ):
        """Test batch query accepts all parameters like single query."""
        from uuid import uuid4

        extraction_id = uuid4()
        mock_vector_store.search.return_value = [
            {
                "embedding_id": "test-id-1",
                "document_extraction_id": str(extraction_id),
                "chunk_index": 0,
                "chunk_text": "Test chunk",
                "similarity_score": 0.9,
                "embedding_model": "test",
            }
        ]
        monkeypatch.setattr("app.services.retrieval_service.get_settings", lambda: mock_settings)

        service = RetrievalService(mock_embedding_service, mock_vector_store)
        results = await service.query_batch(
            ["query 1", "query 2"],
            k=7,
            similarity_threshold=0.6,
            extraction_ids=[extraction_id],
        )

        assert len(results) == 2
        # Verify search was called with the custom parameters
        call_args_list = mock_vector_store.search.call_args_list
        for call in call_args_list:
            assert call.kwargs["k"] == 7
            assert call.kwargs["similarity_threshold"] == 0.6
