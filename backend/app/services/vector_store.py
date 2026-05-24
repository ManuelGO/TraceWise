"""Vector store service for storing and searching embeddings."""

import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, text, update

from app.config import get_settings
from app.models.vector_embedding import EmbeddingData, SearchResult, VectorEmbedding

logger = logging.getLogger(__name__)


class VectorStoreError(Exception):
    """Raised when vector store operations fail."""

    pass


class VectorSearchError(VectorStoreError):
    """Raised when similarity search fails."""

    pass


class VectorStore(ABC):
    """Abstract base class for vector store implementations."""

    @abstractmethod
    async def store_embeddings(self, embeddings: list[EmbeddingData]) -> int:
        """Store embeddings in the vector store.

        Args:
            embeddings: List of embedding data to store

        Returns:
            Number of embeddings successfully stored

        Raises:
            VectorStoreError: If storage fails
        """
        pass

    @abstractmethod
    async def search(
        self, query_vector: list[float], k: int = 5, similarity_threshold: float = 0.0
    ) -> list[SearchResult]:
        """Search for similar embeddings using cosine similarity.

        Args:
            query_vector: Vector to search for
            k: Number of nearest neighbors to return
            similarity_threshold: Minimum similarity score (0.0 to 1.0)

        Returns:
            List of search results ordered by similarity (descending)

        Raises:
            VectorSearchError: If search fails
        """
        pass

    @abstractmethod
    async def delete_by_document_extraction(self, extraction_id: UUID) -> int:
        """Hard delete all embeddings for a document extraction.

        Args:
            extraction_id: DocumentExtraction ID

        Returns:
            Number of embeddings deleted

        Raises:
            VectorStoreError: If deletion fails
        """
        pass

    @abstractmethod
    async def soft_delete_by_document_extraction(self, extraction_id: UUID) -> int:
        """Soft delete all embeddings for a document extraction.

        Args:
            extraction_id: DocumentExtraction ID

        Returns:
            Number of embeddings soft-deleted

        Raises:
            VectorStoreError: If soft deletion fails
        """
        pass

    @abstractmethod
    async def get_by_id(self, embedding_id: UUID) -> EmbeddingData | None:
        """Retrieve an embedding by ID.

        Args:
            embedding_id: VectorEmbedding ID

        Returns:
            EmbeddingData if found, None otherwise

        Raises:
            VectorStoreError: If retrieval fails
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if vector store is operational.

        Returns:
            True if healthy, False otherwise
        """
        pass


class PostgresVectorStore(VectorStore):
    """PostgreSQL vector store using pgvector extension."""

    def __init__(self, session_factory: Any):
        """Initialize PostgreSQL vector store.

        Args:
            session_factory: SQLAlchemy async session factory

        Raises:
            VectorStoreConfigError: If pgvector extension is not available
        """
        self.session_factory = session_factory
        self.settings = get_settings()

    async def store_embeddings(self, embeddings: list[EmbeddingData]) -> int:
        """Store embeddings in PostgreSQL.

        Args:
            embeddings: List of embedding data to store

        Returns:
            Number of embeddings successfully stored

        Raises:
            VectorStoreError: If storage fails
        """
        if not embeddings:
            return 0

        try:
            async with self.session_factory() as session:
                for embedding_data in embeddings:
                    # Validate embedding dimension before storing
                    if len(embedding_data["embedding"]) != 1536:
                        raise VectorStoreError(
                            f"Embedding dimension mismatch: expected 1536, "
                            f"got {len(embedding_data['embedding'])} for chunk_index "
                            f"{embedding_data['chunk_index']}"
                        )

                    vec_embedding = VectorEmbedding(
                        document_extraction_id=UUID(embedding_data["document_extraction_id"]),
                        chunk_index=embedding_data["chunk_index"],
                        embedding=embedding_data["embedding"],
                        embedding_model=embedding_data["embedding_model"],
                        embedding_dim=embedding_data["embedding_dim"],
                        chunk_text=embedding_data["chunk_text"],
                    )
                    session.add(vec_embedding)

                await session.commit()
                logger.info(f"Successfully stored {len(embeddings)} embeddings")
                return len(embeddings)

        except Exception as e:
            logger.error("Failed to store embeddings", exc_info=True)
            raise VectorStoreError("Failed to store embeddings") from e

    async def search(
        self, query_vector: list[float], k: int = 5, similarity_threshold: float = 0.0
    ) -> list[SearchResult]:
        """Search for similar embeddings using cosine similarity.

        Args:
            query_vector: Vector to search for (must be 1536-dimensional for text-embedding-3-small)
            k: Number of nearest neighbors to return (default 5, max 100)
            similarity_threshold: Minimum similarity score (default 0.0, range [0.0, 1.0])

        Returns:
            List of search results ordered by similarity (descending)

        Raises:
            VectorSearchError: If search fails or dimension/bounds mismatch
        """
        if k <= 0:
            return []

        # Cap k to prevent DoS
        max_k = self.settings.VECTOR_SEARCH_DEFAULT_K
        if k > max_k:
            logger.debug(f"Capping k from {k} to {max_k}")
            k = max_k

        if not query_vector:
            raise VectorSearchError("Query vector cannot be empty")

        if len(query_vector) != 1536:
            raise VectorSearchError(
                f"Query vector dimension {len(query_vector)} does not match "
                "expected dimension 1536"
            )

        if not (0.0 <= similarity_threshold <= 1.0):
            raise VectorSearchError(
                f"similarity_threshold must be between 0.0 and 1.0, got {similarity_threshold}"
            )

        try:
            async with self.session_factory() as session:
                # Convert vector to pgvector bracket notation for asyncpg encoding
                query_vector_str = "[" + ",".join(str(v) for v in query_vector) + "]"

                # Use raw SQL for cosine distance calculation
                # <=> operator in pgvector is cosine distance (0 = identical, 2 = opposite)
                # Normalize to [0, 1]: (1 - distance) / 2 maps [0, 2] → [1, 0]
                query = text(
                    """
                    SELECT
                        id,
                        document_extraction_id,
                        chunk_index,
                        chunk_text,
                        embedding_model,
                        (1 - (embedding <=> :query_vector::vector)) / 2 as similarity_score
                    FROM vector_embeddings
                    WHERE deleted_at IS NULL
                    AND ((1 - (embedding <=> :query_vector::vector)) / 2) >= :threshold
                    ORDER BY similarity_score DESC
                    LIMIT :k
                    """
                )

                result = await session.execute(
                    query,
                    {
                        "query_vector": query_vector_str,
                        "threshold": similarity_threshold,
                        "k": k,
                    },
                )

                rows = result.fetchall()
                results: list[SearchResult] = [
                    SearchResult(
                        embedding_id=str(row[0]),
                        document_extraction_id=str(row[1]),
                        chunk_index=row[2],
                        chunk_text=row[3],
                        embedding_model=row[4],
                        similarity_score=float(row[5]),
                    )
                    for row in rows
                ]

                logger.debug(f"Found {len(results)} similar embeddings for query vector")
                return results

        except Exception as e:
            if isinstance(e, VectorSearchError):
                raise
            logger.error("Failed to search embeddings", exc_info=True)
            raise VectorSearchError("Failed to search embeddings") from e

    async def delete_by_document_extraction(self, extraction_id: UUID) -> int:
        """Hard delete all embeddings for a document extraction.

        Args:
            extraction_id: DocumentExtraction ID

        Returns:
            Number of embeddings deleted

        Raises:
            VectorStoreError: If deletion fails
        """
        try:
            async with self.session_factory() as session:
                stmt = delete(VectorEmbedding).where(
                    VectorEmbedding.document_extraction_id == extraction_id
                )
                result = await session.execute(stmt)
                deleted_count = result.rowcount or 0
                await session.commit()

                logger.info(
                    f"Hard deleted {deleted_count} embeddings for extraction {extraction_id}"
                )
                return deleted_count

        except Exception as e:
            logger.error("Failed to delete embeddings", exc_info=True)
            raise VectorStoreError("Failed to delete embeddings") from e

    async def soft_delete_by_document_extraction(self, extraction_id: UUID) -> int:
        """Soft delete all embeddings for a document extraction (idempotent).

        Args:
            extraction_id: DocumentExtraction ID

        Returns:
            Number of embeddings soft-deleted (only counts previously active records)

        Raises:
            VectorStoreError: If soft deletion fails
        """
        try:
            from sqlalchemy import and_

            async with self.session_factory() as session:
                stmt = (
                    update(VectorEmbedding)
                    .where(
                        and_(
                            VectorEmbedding.document_extraction_id == extraction_id,
                            VectorEmbedding.deleted_at.is_(None),  # Only soft-delete active records
                        )
                    )
                    .values(deleted_at=datetime.now(UTC))
                )
                result = await session.execute(stmt)
                deleted_count = result.rowcount or 0
                await session.commit()

                logger.info(
                    f"Soft deleted {deleted_count} embeddings for extraction {extraction_id}"
                )
                return deleted_count

        except Exception as e:
            logger.error("Failed to soft delete embeddings", exc_info=True)
            raise VectorStoreError("Failed to soft delete embeddings") from e

    async def get_by_id(self, embedding_id: UUID) -> EmbeddingData | None:
        """Retrieve an embedding by ID (excluding soft-deleted).

        Args:
            embedding_id: VectorEmbedding ID

        Returns:
            EmbeddingData if found and not soft-deleted, None otherwise

        Raises:
            VectorStoreError: If retrieval fails
        """
        try:
            from sqlalchemy import and_

            async with self.session_factory() as session:
                stmt = select(VectorEmbedding).where(
                    and_(
                        VectorEmbedding.id == embedding_id,
                        VectorEmbedding.deleted_at.is_(None),
                    )
                )
                result = await session.execute(stmt)
                embedding = result.scalar_one_or_none()

                if embedding is None:
                    return None

                embedding_data: EmbeddingData = {
                    "document_extraction_id": str(embedding.document_extraction_id),
                    "chunk_index": embedding.chunk_index,
                    "embedding": list(embedding.embedding),
                    "embedding_model": embedding.embedding_model,
                    "embedding_dim": embedding.embedding_dim,
                    "chunk_text": embedding.chunk_text,
                }
                return embedding_data

        except Exception as e:
            logger.error("Failed to retrieve embedding", exc_info=True)
            raise VectorStoreError("Failed to retrieve embedding") from e

    async def health_check(self) -> bool:
        """Check if vector store is operational.

        Returns:
            True if healthy, False otherwise
        """
        try:
            async with self.session_factory() as session:
                await session.execute(text("SELECT 1"))
                logger.debug("Vector store health check passed")
                return True

        except Exception:
            logger.error("Vector store health check failed", exc_info=True)
            return False
