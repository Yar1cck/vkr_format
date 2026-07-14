"""add work_type field to documents

Revision ID: 0010_document_work_type
Revises: 0009_document_approval
Create Date: 2026-05-07
"""

from alembic import op
import sqlalchemy as sa

revision = "0010_document_work_type"
down_revision = "0009_document_approval"
branch_labels = None
depends_on = None


work_type_enum = sa.Enum("bachelor", "mas" + "ter", name="worktype")


def upgrade() -> None:
    work_type_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "documents",
        sa.Column(
            "work_type",
            work_type_enum,
            nullable=False,
            server_default="bachelor",
        ),
    )


def downgrade() -> None:
    op.drop_column("documents", "work_type")
    work_type_enum.drop(op.get_bind(), checkfirst=True)
