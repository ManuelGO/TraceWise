"""Integration tests for vector store with real database."""

import pytest
from uuid import uuid4

from app.models.vector_embedding import EmbeddingData, VectorEmbedding
from app.services.vector_store import PostgresVectorStore, VectorSearchError


def make_embedding(
    extraction_id: str, chunk_index: int, embedding: list[float], chunk_text: str
) -> EmbeddingData:
    """Factory for creating EmbeddingData test objects."""
    return {
        "document_extraction_id": extraction_id,
        "chunk_index": chunk_index,
        "embedding": embedding,
        "embedding_model": "openai/text-embedding-3-small",
        "embedding_dim": 1536,
        "chunk_text": chunk_text,
    }


@pytest.mark.asyncio
class TestVectorStoreIntegration:
    """Integration tests for PostgreSQL vector store."""

    @pytest.fixture
    def store(self, session_factory):
        """Create a VectorStore instance for testing."""
        return PostgresVectorStore(session_factory)

    async def test_vector_store_health_check(self, store):
        """Test vector store health check."""
        is_healthy = await store.health_check()
        assert is_healthy is True

    async def test_store_and_retrieve_single_embedding(self, store):
        """Test storing and retrieving a single embedding."""
        extraction_id = str(uuid4())
        query_vector = [0.1] * 1536

        embeddings: list[EmbeddingData] = [
            make_embedding(extraction_id, 0, query_vector, "test chunk")
        ]

        # Store embeddings
        stored_count = await store.store_embeddings(embeddings)
        assert stored_count == 1

        # Retrieve should find it
        results = await store.search(query_vector=query_vector, k=5)
        assert len(results) == 1
        assert results[0]["chunk_text"] == "test chunk"
        assert 0.99 <= results[0]["similarity_score"] <= 1.0

    async def test_store_multiple_embeddings_batch(self, store):
        """Test storing multiple embeddings in batch."""
        extraction_id = str(uuid4())

        embeddings: list[EmbeddingData] = [
            make_embedding(extraction_id, i, [0.1 * (i + 1)] * 1536, f"chunk {i}")
            for i in range(5)
        ]

        stored_count = await store.store_embeddings(embeddings)
        assert stored_count == 5

    async def test_search_returns_k_results(self, store):
        """Test that search returns exactly k results."""
        extraction_id = str(uuid4())
        query_vector = [0.1] * 1536

        # Store 10 embeddings
        embeddings: list[EmbeddingData] = [
            make_embedding(extraction_id, i, [0.1] * 1536, f"chunk {i}")
            for i in range(10)
        ]

        await store.store_embeddings(embeddings)

        # Search with k=3
        results = await store.search(query_vector=query_vector, k=3)
        assert len(results) == 3

    async def test_search_respects_similarity_threshold(self, store):
        """Test that search respects similarity threshold."""
        extraction_id = str(uuid4())
        query_vector = [0.1] * 1536

        # Store embeddings with varying similarity
        embeddings: list[EmbeddingData] = [
            make_embedding(extraction_id, 0, query_vector, "identical"),
            make_embedding(extraction_id, 1, [0.05] * 1536, "different"),
        ]

        await store.store_embeddings(embeddings)

        # Search with high threshold
        results = await store.search(
            query_vector=query_vector, k=10, similarity_threshold=0.99
        )
        assert len(results) == 1
        assert results[0]["chunk_text"] == "identical"

    async def test_soft_delete_excludes_results(self, store):
        """Test that soft-deleted embeddings are excluded from search."""
        extraction_id = str(uuid4())
        query_vector = [0.1] * 1536

        embeddings: list[EmbeddingData] = [
            make_embedding(extraction_id, 0, query_vector, "chunk 1"),
            make_embedding(extraction_id, 1, [0.15] * 1536, "chunk 2"),
        ]

        await store.store_embeddings(embeddings)

        # Soft delete one extraction
        deleted_count = await store.soft_delete_by_document_extraction(extraction_id)
        assert deleted_count == 2

        # Search should return no results
        results = await store.search(query_vector=query_vector, k=10)
        assert len(results) == 0

    async def test_hard_delete_removes_embeddings(self, store):
        """Test that hard delete removes embeddings."""
        extraction_id = str(uuid4())
        query_vector = [0.1] * 1536

        embeddings: list[EmbeddingData] = [
            make_embedding(extraction_id, 0, query_vector, "chunk 1")
        ]

        await store.store_embeddings(embeddings)

        # Hard delete
        deleted_count = await store.delete_by_document_extraction(extraction_id)
        assert deleted_count == 1

        # Search should return no results
        results = await store.search(query_vector=query_vector, k=10)
        assert len(results) == 0

    async def test_get_by_id_returns_embedding_data(self, store, session_factory):
        """Test get_by_id returns EmbeddingData."""
        extraction_id = str(uuid4())
        query_vector = [0.1] * 1536

        embeddings: list[EmbeddingData] = [
            make_embedding(extraction_id, 0, query_vector, "test chunk")
        ]

        await store.store_embeddings(embeddings)

        # Get the embedding by querying
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import AsyncSession

        async with session_factory() as session:
            stmt = select(VectorEmbedding).limit(1)
            result = await session.execute(stmt)
            embedding = result.scalar_one()

            # Now get it via store
            retrieved = await store.get_by_id(embedding.id)
            assert retrieved is not None
            assert retrieved["chunk_text"] == "test chunk"
            assert retrieved["embedding_dim"] == 1536

    async def test_search_results_ordered_by_similarity(self, store):
        """Test that search results are ordered by similarity descending."""
        extraction_id = str(uuid4())
        query_vector = [1.0] * 1536

        embeddings: list[EmbeddingData] = [
            make_embedding(extraction_id, i, [0.5 + 0.01 * i] * 1536, f"chunk {i}")
            for i in range(5)
        ]

        await store.store_embeddings(embeddings)

        results = await store.search(query_vector=query_vector, k=5)
        assert len(results) == 5

        # Check ordering (descending by similarity)
        for i in range(len(results) - 1):
            assert results[i]["similarity_score"] >= results[i + 1]["similarity_score"]

    async def test_empty_database_returns_empty_results(self, store):
        """Test search on empty database returns empty results."""
        query_vector = [0.1] * 1536

        results = await store.search(query_vector=query_vector, k=5)
        assert results == []
