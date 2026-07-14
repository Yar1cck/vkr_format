"""communication: review_rounds, document_comments, violation supervisor_comment

Revision ID: 0011_communication
Revises: 0010_document_work_type
Create Date: 2026-05-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011_communication"
down_revision = "0010_document_work_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_rounds",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decided_by_name", sa.String(255), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_rounds_document_id", "review_rounds", ["document_id"])

    op.create_table(
        "document_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_name", sa.String(255), nullable=False),
        sa.Column("author_role", sa.String(32), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_comments_document_id", "document_comments", ["document_id"])

    op.add_column(
        "violation_records",
        sa.Column("supervisor_comment", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("violation_records", "supervisor_comment")
    op.drop_index("ix_document_comments_document_id", table_name="document_comments")
    op.drop_table("document_comments")
    op.drop_index("ix_review_rounds_document_id", table_name="review_rounds")
    op.drop_table("review_rounds")
