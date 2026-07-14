"""add fix_options to violation_records

Revision ID: 0002_violation_fix_options
Revises: 0001_initial
Create Date: 2026-04-21
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_violation_fix_options"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "violation_records",
        sa.Column("fix_options", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("violation_records", "fix_options")
