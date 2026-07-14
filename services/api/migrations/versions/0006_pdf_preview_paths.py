"""add pdf preview paths for Word-accurate client rendering

Revision ID: 0006_pdf_preview_paths
Revises: 0005_drop_html_preview_paths
Create Date: 2026-04-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_pdf_preview_paths"
down_revision = "0002_violation_fix_options"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("processing_reports", sa.Column("original_pdf_storage_path", sa.Text(), nullable=True))
    op.add_column("processing_reports", sa.Column("processed_pdf_storage_path", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("processing_reports", "original_pdf_storage_path")
    op.drop_column("processing_reports", "processed_pdf_storage_path")
