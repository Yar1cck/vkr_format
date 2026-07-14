"""document_snapshots: undo history for manual document fixes

Revision ID: 0012_document_snapshots
Revises: 0011_communication
Create Date: 2026-05-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0012_document_snapshots"
down_revision = "0011_communication"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_index", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("action_description", sa.Text(), nullable=False),
        sa.Column("processed_storage_path", sa.Text(), nullable=False),
        sa.Column("processed_pdf_storage_path", sa.Text(), nullable=True),
        sa.Column("violation_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_snapshots_document_id", "document_snapshots", ["document_id"])
    op.create_index(
        "ix_document_snapshots_doc_idx",
        "document_snapshots",
        ["document_id", "snapshot_index"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_snapshots_doc_idx", table_name="document_snapshots")
    op.drop_index("ix_document_snapshots_document_id", table_name="document_snapshots")
    op.drop_table("document_snapshots")
