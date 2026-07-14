"""user_supervisor: add supervisor_id to users table

Revision ID: 0013_user_supervisor
Revises: 0012_document_snapshots
Create Date: 2026-05-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0013_user_supervisor"
down_revision = "0012_document_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Не FK — при удалении пользователя-руководителя история привязки
    # студентов не должна ломаться (аналогично decided_by в review_rounds).
    op.add_column(
        "users",
        sa.Column("supervisor_id", postgresql.UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "supervisor_id")
