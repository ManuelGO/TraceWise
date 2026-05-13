"""Create documents table

Revision ID: 002
Revises: 001
Create Date: 2026-05-12

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create documents table."""
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("case_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column(
            "document_type",
            sa.Enum(
                "supplier_declaration",
                "invoice",
                "shipment_note",
                "geojson",
                "certificate",
                "other",
                name="documenttype",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("storage_path", sa.String(length=512), nullable=False),
        sa.Column(
            "processing_status",
            sa.Enum(
                "pending",
                "processing",
                "completed",
                "failed",
                name="processingstatus",
                native_enum=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["compliance_cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_documents_id"), "documents", ["id"], unique=False)
    op.create_index(op.f("ix_documents_case_id"), "documents", ["case_id"], unique=False)
    op.create_index(
        op.f("ix_documents_document_type"), "documents", ["document_type"], unique=False
    )
    op.create_index(
        op.f("ix_documents_processing_status"),
        "documents",
        ["processing_status"],
        unique=False,
    )
    op.create_index(op.f("ix_documents_uploaded_at"), "documents", ["uploaded_at"], unique=False)


def downgrade() -> None:
    """Drop documents table."""
    op.drop_index(op.f("ix_documents_uploaded_at"), table_name="documents")
    op.drop_index(op.f("ix_documents_processing_status"), table_name="documents")
    op.drop_index(op.f("ix_documents_document_type"), table_name="documents")
    op.drop_index(op.f("ix_documents_case_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_id"), table_name="documents")
    op.drop_table("documents")
