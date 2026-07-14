"""add approval workflow fields to documents (S-18)

Revision ID: 0009_document_approval
Revises: 0008_violation_detector_signals
Create Date: 2026-05-06
"""

from alembic import op
import sqlalchemy as sa

revision = "0009_document_approval"
down_revision = "0008_violation_detector_signals"
branch_labels = None
depends_on = None


approval_status_enum = sa.Enum(
    "pending_review", "approved", "rejected",
    name="approvalstatus",
)


def upgrade() -> None:
    approval_status_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "documents",
        sa.Column("approval_status", approval_status_enum, nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("approval_comment", sa.Text(), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column(
            "approval_decided_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "documents",
        sa.Column(
            "approval_decided_by",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("documents", "approval_decided_by")
    op.drop_column("documents", "approval_decided_at")
    op.drop_column("documents", "approval_comment")
    op.drop_column("documents", "approval_status")
    approval_status_enum.drop(op.get_bind(), checkfirst=True)
