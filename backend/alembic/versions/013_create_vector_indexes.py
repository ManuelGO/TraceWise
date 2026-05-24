"""Create indexes on vector_embeddings table.

This migration:
- Creates index on document_extraction_id for FK lookups
- Creates index on created_at for cleanup operations
- Creates index on deleted_at for filtering soft-deleted records
- Creates IVFFlat vector index for cosine similarity search

Note: Uses created_at, updated_at, and sa.Uuid(as_uuid=True), sa.DateTime(timezone=True)
from the vector_embeddings table created in migration 012.

Revision ID: 013
Revises: 012
Create Date: 2026-05-24
Updated_at: 2026-05-24

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "013"
down_revision: str | None = "012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create indexes on vector_embeddings table."""
    # Index on created_at for cleanup operations and time-based queries
    op.create_index(
        "idx_vector_embeddings_created_at",
        "vector_embeddings",
        ["created_at"],
    )

    # Index on deleted_at for filtering soft-deleted records
    op.create_index(
        "idx_vector_embeddings_deleted_at",
        "vector_embeddings",
        ["deleted_at"],
    )

    # IVFFlat index for cosine similarity search
    # Using vector_cosine_ops for cosine distance metric
    # lists=100 is a good default for medium datasets (<1M vectors)
    op.execute(
        """
        CREATE INDEX idx_vector_embeddings_vector_ivfflat
        ON vector_embeddings
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
        """
    )


def downgrade() -> None:
    """Drop indexes on vector_embeddings table."""
    # Drop IVFFlat vector index
    op.drop_index(
        "idx_vector_embeddings_vector_ivfflat",
        "vector_embeddings",
    )

    # Drop deleted_at index
    op.drop_index(
        "idx_vector_embeddings_deleted_at",
        "vector_embeddings",
    )

    # Drop created_at index
    op.drop_index(
        "idx_vector_embeddings_created_at",
        "vector_embeddings",
    )
