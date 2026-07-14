"""add detector_signals to violation_records (explainability, A-N2)

Revision ID: 0008_violation_detector_signals
Revises: 0007_violation_caused_by_index
Create Date: 2026-05-06
"""

from alembic import op
import sqlalchemy as sa

revision = "0008_violation_detector_signals"
down_revision = "0007_violation_caused_by_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Список сработавших сигналов скоринга (например,
    # ["literal_number:1.2.1", "bold:0.95", "centered", "isolated"]).
    # Используется UI для раскрывашки «Почему это распознано как заголовок» —
    # сильный аргумент про прозрачность алгоритма (ТЗ §1.3).
    op.add_column(
        "violation_records",
        sa.Column("detector_signals", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("violation_records", "detector_signals")
