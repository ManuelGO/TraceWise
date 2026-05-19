"""Document repository for specialized data access patterns."""

from typing import ClassVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import BaseRepository
from app.models import Document, DocumentType, ProcessingStatus


class DocumentRepository(BaseRepository[Document]):
    """Repository for Document with specialized query methods.

    Allowed filter fields:
    - case_id: Filter by parent compliance case (required for multi-tenancy isolation)
    - document_type: Filter by document type (supplier_declaration, invoice, shipment_note, etc.)
    - processing_status: Filter by processing status (uploaded, validating, extracting, extracted, embedding, ready, failed)
    """

    FILTERABLE_FIELDS: ClassVar[set[str]] = {"case_id", "document_type", "processing_status"}

    def __init__(self):
        """Initialize repository for Document model."""
        super().__init__(Document)

    async def find_by_case_id(
        self,
        session: AsyncSession,
        case_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Document]:
        """Find all documents for a given compliance case.

        Args:
            session: AsyncSession instance
            case_id: ComplianceCase ID to search for
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of Document instances for the given case
        """
        return await self.list_by_filter(session, skip=skip, limit=limit, case_id=case_id)

    async def find_by_type(
        self,
        session: AsyncSession,
        document_type: DocumentType,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Document]:
        """Find all documents of a specific type.

        Args:
            session: AsyncSession instance
            document_type: DocumentType to filter by
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of Document instances of the given type
        """
        return await self.list_by_filter(
            session, skip=skip, limit=limit, document_type=document_type
        )

    async def find_by_processing_status(
        self,
        session: AsyncSession,
        status: ProcessingStatus,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Document]:
        """Find all documents with the given processing status.

        Args:
            session: AsyncSession instance
            status: ProcessingStatus to filter by
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of Document instances with the given status
        """
        return await self.list_by_filter(session, skip=skip, limit=limit, processing_status=status)

    async def find_uploaded_documents(
        self, session: AsyncSession, skip: int = 0, limit: int = 100
    ) -> list[Document]:
        """Find all documents in UPLOADED status (ready for processing).

        Args:
            session: AsyncSession instance
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of Document instances with UPLOADED status
        """
        return await self.find_by_processing_status(
            session, ProcessingStatus.UPLOADED, skip=skip, limit=limit
        )


__all__ = ["DocumentRepository"]
