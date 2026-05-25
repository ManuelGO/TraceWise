"""Vector embedding model for storing document chunk embeddings."""

from typing import Any, TypedDict
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, relationship

from app.db.database import Base
from app.models.base import BaseModel


class EmbeddingData(TypedDict):
    """Input data for storing an embedding."""

    document_extraction_id: str
    chunk_index: int
    embedding: list[float]
    embedding_model: str
    embedding_dim: int
    chunk_text: str


class SearchResult(TypedDict):
    """Output data from similarity search."""

    embedding_id: str
    document_extraction_id: str
    chunk_index: int
    chunk_text: str
    similarity_score: float
    embedding_model: str


class VectorEmbedding(Base, BaseModel):
    """Domain model for storing vector embeddings of document chunks."""

    __tablename__ = "vector_embeddings"

    __table_args__ = (
        UniqueConstraint(
            "document_extraction_id", "chunk_index",
            name="uq_vector_embeddings_extraction_chunk",
        ),
    )

    id: Mapped = Column(  # type: ignore[assignment]
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    document_extraction_id: Mapped = Column(  # type: ignore[assignment]
        Uuid(as_uuid=True),
        ForeignKey("document_extractions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index = Column(Integer, nullable=False)
    embedding: Any = Column(Vector(1536), nullable=False)
    embedding_model = Column(String(255), nullable=False)
    embedding_dim = Column(Integer, nullable=False)
    chunk_text = Column(Text, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    document_extraction = relationship(
        "DocumentExtraction",
        foreign_keys=[document_extraction_id],
        lazy="joined",
    )

    def __repr__(self):
        return (
            f"<VectorEmbedding(id={self.id}, "
            f"document_extraction_id={self.document_extraction_id}, "
            f"chunk_index={self.chunk_index}, "
            f"embedding_model={self.embedding_model}, "
            f"embedding_dim={self.embedding_dim})>"
        )
