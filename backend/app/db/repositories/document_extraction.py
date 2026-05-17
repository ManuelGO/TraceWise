"""Document extraction repository for specialized data access patterns."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import BaseRepository
from app.models import DocumentExtraction


class DocumentExtractionRepository(BaseRepository[DocumentExtraction]):
    """Repository for DocumentExtraction with specialized query methods."""

    def __init__(self):
        """Initialize repository for DocumentExtraction model."""
        super().__init__(DocumentExtraction)

    async def read_by_idempotency_key(
        self,
        session: AsyncSession,
        key: str,
    ) -> DocumentExtraction | None:
        """Fetch extraction by idempotency key (for Task 27 deduplication).

        Args:
            session: AsyncSession instance
            key: Idempotency key to search for

        Returns:
            DocumentExtraction instance if found, None otherwise
        """
        stmt = select(DocumentExtraction).where(DocumentExtraction.idempotency_key == key)
        result = await session.execute(stmt)
        return result.scalars().first()

    async def read_by_document_id(
        self,
        session: AsyncSession,
        document_id: str,
    ) -> DocumentExtraction | None:
        """Fetch latest extraction for a document.

        Args:
            session: AsyncSession instance
            document_id: Document ID to search for

        Returns:
            DocumentExtraction instance if found, None otherwise
        """
        stmt = (
            select(DocumentExtraction)
            .where(DocumentExtraction.document_id == document_id)
            .order_by(DocumentExtraction.created_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalars().first()


__all__ = ["DocumentExtractionRepository"]
