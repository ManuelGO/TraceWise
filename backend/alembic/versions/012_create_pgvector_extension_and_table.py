"""Create pgvector extension and vector_embeddings table.

This migration:
- Enables pgvector extension for vector similarity search
- Creates vector_embeddings table for storing document chunk embeddings
- Adds composite unique index on (document_extraction_id, chunk_index)
- Adds soft-delete support with deleted_at column
- Adds foreign key constraint with CASCADE delete on document_extractions

Revision ID: 012
Revises: 011
Create Date: 2026-05-24
Updated_at: 2026-05-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "012"
down_revision: str | None = "011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create pgvector extension and vector_embeddings table."""
    # Create pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Create vector_embeddings table
    op.create_table(
        "vector_embeddings",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            nullable=False,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "document_extraction_id",
            sa.Uuid(as_uuid=True),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "chunk_index",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "embedding",
            Vector(1536),
            nullable=False,
        ),
        sa.Column(
            "embedding_model",
            sa.String(255),
            nullable=False,
        ),
        sa.Column(
            "embedding_dim",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "chunk_text",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        # Foreign key constraint with CASCADE delete
        sa.ForeignKeyConstraint(
            ["document_extraction_id"],
            ["document_extractions.id"],
            ondelete="CASCADE",
        ),
        # Composite unique constraint
        sa.UniqueConstraint(
            "document_extraction_id",
            "chunk_index",
            name="uq_vector_embeddings_extraction_chunk",
        ),
    )


def downgrade() -> None:
    """Drop vector_embeddings table and pgvector extension."""
    # Drop table
    op.drop_table("vector_embeddings")

    # Drop pgvector extension
    op.execute("DROP EXTENSION IF EXISTS vector")
