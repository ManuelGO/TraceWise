"""Repository for VectorEmbedding model."""

import logging
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import BaseRepository
from app.models.vector_embedding import VectorEmbedding

logger = logging.getLogger(__name__)


class VectorEmbeddingRepository(BaseRepository[VectorEmbedding]):
    """Repository for vector embedding operations."""

    FILTERABLE_FIELDS: ClassVar[set[str]] = {"document_extraction_id", "embedding_model", "deleted_at"}

    def __init__(self):
        """Initialize repository for VectorEmbedding."""
        super().__init__(VectorEmbedding)

    async def get_by_id(self, session: AsyncSession, embedding_id: UUID) -> VectorEmbedding | None:
        """Get embedding by ID (excluding soft-deleted).

        Args:
            session: AsyncSession instance
            embedding_id: VectorEmbedding ID

        Returns:
            VectorEmbedding if found and not soft-deleted, None otherwise
        """
        stmt = select(self.model).where(
            and_(
                self.model.id == embedding_id,
                self.model.deleted_at.is_(None),
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_extraction(
        self, session: AsyncSession, extraction_id: UUID
    ) -> list[VectorEmbedding]:
        """Get all embeddings for a document extraction (excluding soft-deleted).

        Args:
            session: AsyncSession instance
            extraction_id: DocumentExtraction ID

        Returns:
            List of VectorEmbedding instances
        """
        stmt = select(self.model).where(
            and_(
                self.model.document_extraction_id == extraction_id,
                self.model.deleted_at.is_(None),
            )
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def soft_delete(self, session: AsyncSession, embedding_id: UUID) -> bool:
        """Soft delete an embedding by ID (idempotent).

        Args:
            session: AsyncSession instance
            embedding_id: VectorEmbedding ID

        Returns:
            True if soft-deleted, False if not found or already deleted
        """
        stmt = (
            update(self.model)
            .where(
                and_(
                    self.model.id == embedding_id,
                    self.model.deleted_at.is_(None),
                )
            )
            .values(deleted_at=datetime.now(UTC))
        )
        result = await session.execute(stmt)
        await session.flush()
        return (result.rowcount or 0) > 0

    async def soft_delete_by_extraction(self, session: AsyncSession, extraction_id: UUID) -> int:
        """Soft delete all embeddings for a document extraction.

        Args:
            session: AsyncSession instance
            extraction_id: DocumentExtraction ID

        Returns:
            Number of embeddings soft-deleted
        """
        stmt = (
            update(self.model)
            .where(self.model.document_extraction_id == extraction_id)
            .values(deleted_at=datetime.now(UTC))
        )
        result = await session.execute(stmt)
        await session.flush()
        return result.rowcount or 0

    async def hard_delete(self, session: AsyncSession, embedding_id: UUID) -> bool:
        """Hard delete an embedding by ID.

        Args:
            session: AsyncSession instance
            embedding_id: VectorEmbedding ID

        Returns:
            True if deleted, False if not found
        """
        stmt = delete(self.model).where(self.model.id == embedding_id)
        result = await session.execute(stmt)
        await session.flush()
        return (result.rowcount or 0) > 0

    async def hard_delete_by_extraction(self, session: AsyncSession, extraction_id: UUID) -> int:
        """Hard delete all embeddings for a document extraction.

        Args:
            session: AsyncSession instance
            extraction_id: DocumentExtraction ID

        Returns:
            Number of embeddings deleted
        """
        stmt = delete(self.model).where(self.model.document_extraction_id == extraction_id)
        result = await session.execute(stmt)
        await session.flush()
        return result.rowcount or 0

    async def list_soft_deleted(
        self, session: AsyncSession, older_than: datetime | None = None
    ) -> list[VectorEmbedding]:
        """List soft-deleted embeddings, optionally filtered by age.

        Args:
            session: AsyncSession instance
            older_than: Optional datetime to filter (return records deleted before this time)

        Returns:
            List of soft-deleted VectorEmbedding instances
        """
        stmt = select(self.model).where(self.model.deleted_at.isnot(None))
        if older_than:
            stmt = stmt.where(self.model.deleted_at < older_than)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_extraction(self, session: AsyncSession, extraction_id: UUID) -> int:
        """Count embeddings for a document extraction (excluding soft-deleted).

        Args:
            session: AsyncSession instance
            extraction_id: DocumentExtraction ID

        Returns:
            Count of active embeddings
        """
        stmt = select(func.count(self.model.id)).where(
            and_(
                self.model.document_extraction_id == extraction_id,
                self.model.deleted_at.is_(None),
            )
        )
        result = await session.execute(stmt)
        return result.scalar() or 0
