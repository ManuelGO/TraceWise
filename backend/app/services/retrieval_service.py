"""Retrieval service for RAG query processing.

This module provides the core retrieval pipeline for the RAG system:
1. Query embedding: Convert user queries to vector embeddings
2. Vector search: Find similar document chunks using cosine similarity
3. Metadata filtering: Filter by document extraction or soft-delete status
4. Result ranking: Return results ordered by similarity (descending)

The service supports both single and batch query operations with configurable
concurrency limits and similarity thresholds.
"""

import asyncio
import logging
import time
from uuid import UUID

from app.config import get_settings
from app.models.vector_embedding import SearchResult
from app.services.embedding_service import EmbeddingError, EmbeddingService
from app.services.vector_store import VectorSearchError, VectorStore

logger = logging.getLogger(__name__)


class RetrievalError(Exception):
    """Raised when retrieval pipeline operations fail."""

    pass


class RetrievalService:
    """Orchestrator for the RAG retrieval pipeline.

    Composes EmbeddingService and VectorStore to execute complete retrieval
    queries: converts user queries to embeddings, searches the vector store,
    filters results, and returns ranked documents.

    Supports single and batch query operations with configurable parameters
    for result count, similarity threshold, and concurrent batch size.
    """

    def __init__(self, embedding_service: EmbeddingService, vector_store: VectorStore):
        """Initialize retrieval service.

        Args:
            embedding_service: Service for generating query embeddings
            vector_store: Backend for similarity search

        Raises:
            ValueError: If services are not properly initialized
        """
        if not embedding_service:
            raise ValueError("embedding_service cannot be None")
        if not vector_store:
            raise ValueError("vector_store cannot be None")

        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.settings = get_settings()

    async def query(
        self,
        query: str,
        k: int | None = None,
        similarity_threshold: float | None = None,
        extraction_ids: list[UUID] | None = None,
    ) -> list[SearchResult]:
        """Execute a single retrieval query.

        Args:
            query: User query string
            k: Number of results to return (uses default if None)
            similarity_threshold: Minimum similarity score (uses default if None)
            extraction_ids: Filter to specific document extractions

        Returns:
            List of SearchResult ordered by similarity (descending)

        Raises:
            RetrievalError: If k <= 0, query embedding fails, or search fails
        """
        if not query or not query.strip():
            raise RetrievalError("Query cannot be empty")

        if k is None:
            k = self.settings.RETRIEVAL_DEFAULT_K

        if k <= 0:
            raise RetrievalError("k must be a positive integer")

        if similarity_threshold is None:
            similarity_threshold = self.settings.RETRIEVAL_SIMILARITY_THRESHOLD
        if not (0.0 <= similarity_threshold <= 1.0):
            raise RetrievalError(f"Similarity threshold must be between 0.0 and 1.0, got {similarity_threshold}")

        try:
            start_time = time.time()

            query_embedding = await self.embedding_service.embed_query(query.strip())

            results = await self.vector_store.search(query_embedding, k=k, similarity_threshold=similarity_threshold)

            if extraction_ids:
                results = [r for r in results if UUID(r["document_extraction_id"]) in extraction_ids]

            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.info(
                f"Query executed: {len(results)} results in {elapsed_ms}ms",
                extra={
                    "query_length": len(query),
                    "k": k,
                    "threshold": similarity_threshold,
                    "results_count": len(results),
                    "elapsed_ms": elapsed_ms,
                    "avg_similarity": sum(r["similarity_score"] for r in results) / len(results) if results else 0,
                },
            )

            return results

        except EmbeddingError as e:
            logger.error("Failed to embed query", exc_info=True)
            raise RetrievalError("Failed to embed query") from e
        except VectorSearchError as e:
            logger.error("Failed to search vector store", exc_info=True)
            raise RetrievalError("Failed to search vector store") from e

    async def query_batch(
        self,
        queries: list[str],
        k: int | None = None,
        similarity_threshold: float | None = None,
        extraction_ids: list[UUID] | None = None,
    ) -> list[list[SearchResult]]:
        """Execute multiple retrieval queries concurrently.

        Runs up to RETRIEVAL_BATCH_SIZE queries in parallel using a semaphore
        to prevent resource exhaustion.

        Args:
            queries: List of query strings
            k: Number of results per query (uses default if None)
            similarity_threshold: Minimum similarity score (uses default if None)
            extraction_ids: Filter to specific document extractions

        Returns:
            List of result lists, one per query (same order as input)

        Raises:
            RetrievalError: If any query fails
        """
        if not queries:
            return []

        start_time = time.time()
        semaphore = asyncio.Semaphore(self.settings.RETRIEVAL_BATCH_SIZE)

        async def query_with_limit(query: str) -> list[SearchResult]:
            async with semaphore:
                return await self.query(query, k=k, similarity_threshold=similarity_threshold, extraction_ids=extraction_ids)

        try:
            results = await asyncio.gather(*[query_with_limit(q) for q in queries])
            elapsed = time.time() - start_time
            total_results = sum(len(r) for r in results)

            logger.info(
                f"Batch query executed: {len(queries)} queries -> {total_results} total results in {int(elapsed * 1000)}ms",
                extra={
                    "batch_size": len(queries),
                    "total_results": total_results,
                    "elapsed_ms": int(elapsed * 1000),
                    "avg_results_per_query": total_results / len(queries),
                },
            )

            return results
        except Exception as e:
            logger.error("Batch query failed", exc_info=True)
            raise RetrievalError("Batch query failed") from e
