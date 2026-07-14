"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("role", sa.Enum("student", "supervisor", "dean", "admin", name="userrole"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "normative_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("rules_config", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("original_format", sa.String(length=16), nullable=False),
        sa.Column("original_storage_path", sa.Text(), nullable=False),
        sa.Column("processed_storage_path", sa.Text(), nullable=True),
        sa.Column("status", sa.Enum("pending", "processing", "done", "error", name="documentstatus"), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("normative_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("normative_versions.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processing_mode", sa.Enum("full", "check_only", name="processingmode"), nullable=False),
        sa.Column("processing_error", sa.Text(), nullable=True),
    )

    op.create_table(
        "processing_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_violations", sa.Integer(), nullable=False),
        sa.Column("auto_fixed", sa.Integer(), nullable=False),
        sa.Column("manual_required", sa.Integer(), nullable=False),
        sa.Column("report_storage_path", sa.Text(), nullable=False),
        sa.Column("report_pdf_storage_path", sa.Text(), nullable=True),
        sa.Column("diff_storage_path", sa.Text(), nullable=True),
        sa.Column("volume_pages", sa.Integer(), nullable=True),
    )

    op.create_table(
        "violation_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("processing_reports.id"), nullable=False),
        sa.Column("type", sa.String(length=128), nullable=False),
        sa.Column("rule_reference", sa.String(length=128), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("paragraph_index", sa.Integer(), nullable=True),
        sa.Column("section_title", sa.String(length=255), nullable=True),
        sa.Column("original_text", sa.Text(), nullable=True),
        sa.Column("fixed_text", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("auto_fixed", "manual_required", "accepted", "rejected", name="violationstatus"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("violation_records")
    op.drop_table("processing_reports")
    op.drop_table("documents")
    op.drop_table("normative_versions")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
