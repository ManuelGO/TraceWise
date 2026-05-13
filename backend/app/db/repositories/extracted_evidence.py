"""ExtractedEvidence repository for specialized data access patterns."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import BaseRepository
from app.models import ExtractedEvidence


class ExtractedEvidenceRepository(BaseRepository[ExtractedEvidence]):
    """Repository for ExtractedEvidence with specialized query methods.

    Allowed filter fields:
    - case_id: Filter by parent compliance case
    - document_id: Filter by parent document (for tracking evidence source)
    - evidence_type: Filter by evidence type (compliance_indicator, risk_flag, etc.)
    """

    def __init__(self):
        """Initialize repository for ExtractedEvidence model."""
        super().__init__(ExtractedEvidence)
        # Define which fields can be filtered on
        self.FILTERABLE_FIELDS = {"case_id", "document_id", "evidence_type"}

    async def find_by_case_id(
        self,
        session: AsyncSession,
        case_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ExtractedEvidence]:
        """Find all extracted evidence for a given compliance case.

        Args:
            session: AsyncSession instance
            case_id: ComplianceCase ID to search for
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of ExtractedEvidence instances for the given case
        """
        return await self.list_by_filter(session, skip=skip, limit=limit, case_id=case_id)

    async def find_by_document_id(
        self,
        session: AsyncSession,
        document_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ExtractedEvidence]:
        """Find all evidence extracted from a specific document.

        Args:
            session: AsyncSession instance
            document_id: Document ID to search for
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of ExtractedEvidence instances from the given document
        """
        return await self.list_by_filter(session, skip=skip, limit=limit, document_id=document_id)

    async def find_by_evidence_type(
        self,
        session: AsyncSession,
        evidence_type: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ExtractedEvidence]:
        """Find all evidence of a specific type.

        Args:
            session: AsyncSession instance
            evidence_type: Type of evidence to filter by
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of ExtractedEvidence instances of the given type
        """
        return await self.list_by_filter(
            session, skip=skip, limit=limit, evidence_type=evidence_type
        )


__all__ = ["ExtractedEvidenceRepository"]
