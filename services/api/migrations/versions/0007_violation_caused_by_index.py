"""add caused_by_index to violation_records (cascade collapse, A-D2)

Revision ID: 0007_violation_caused_by_index
Revises: 0006_pdf_preview_paths
Create Date: 2026-05-06
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_violation_caused_by_index"
down_revision = "0006_pdf_preview_paths"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Каскадные нарушения нумерации заголовков ссылаются на paragraph_index
    # первого нарушения в каскаде. NULL означает «это самостоятельное
    # нарушение» (либо корень каскада, либо нарушение другого типа).
    op.add_column(
        "violation_records",
        sa.Column("caused_by_index", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("violation_records", "caused_by_index")
