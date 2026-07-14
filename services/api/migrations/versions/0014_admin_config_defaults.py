"""sync admin configuration defaults with runtime behavior

Revision ID: 0014_admin_config_defaults
Revises: 0013_user_supervisor
Create Date: 2026-05-27
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa

revision = "0014_admin_config_defaults"
down_revision = "0013_user_supervisor"
branch_labels = None
depends_on = None


_META = {
    "version": "v2.0.0",
    "name": "МИИГАиК — Приказ №697-01 от 29.12.2023",
    "effective_date": "2026-04-01",
    "reference": "Приказ №697-01 от 29.12.2023",
}

_NON_BACHELOR_TITLE_MARKERS = {
    "\u043c\u0430\u0433\u0438\u0441\u0442\u0435\u0440\u0441\u043a\u0430\u044f \u0434\u0438\u0441\u0441\u0435\u0440\u0442\u0430\u0446\u0438\u044f",
    "\u043c\u0430\u0433\u0438\u0441\u0442\u0435\u0440\u0441\u043a\u0430\u044f \u0440\u0430\u0431\u043e\u0442\u0430",
    "\u0432\u043a\u0440 \u043c\u0430\u0433\u0438\u0441\u0442\u0440\u0430",
}


def _norm(text: object) -> str:
    return " ".join(str(text).strip().lower().split())


def _sync_rules(rules: dict) -> dict:
    out = dict(rules or {})
    out["meta"] = dict(_META)

    structural = dict(out.get("structural_elements") or {})
    title_page = structural.get("title_page")
    if isinstance(title_page, list):
        structural["title_page"] = [
            item for item in title_page
            if _norm(item) not in _NON_BACHELOR_TITLE_MARKERS
        ]
    out["structural_elements"] = structural

    numbering = dict(out.get("numbering_rules") or {})
    numbering.pop("formula_mode", None)
    numbering["figure_mode"] = "by_chapter"
    numbering["table_mode"] = "by_chapter"
    numbering["listing_mode"] = "by_chapter"
    numbering.setdefault("validate_citation_sequence", True)
    out["numbering_rules"] = numbering

    volume = out.get("volume_limits") or {}
    if isinstance(volume, dict) and isinstance(volume.get("bachelor"), dict):
        bachelor = volume["bachelor"]
        out["volume_limits"] = {
            "min": bachelor.get("min", 40),
            "max": bachelor.get("max", 120),
        }
    else:
        out["volume_limits"] = {
            "min": (volume or {}).get("min", 40) if isinstance(volume, dict) else 40,
            "max": (volume or {}).get("max", 120) if isinstance(volume, dict) else 120,
        }

    return out


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, rules_config FROM normative_versions")).mappings()
    for row in rows:
        rules = row["rules_config"]
        if isinstance(rules, str):
            rules = json.loads(rules)
        synced = _sync_rules(rules)
        bind.execute(
            sa.text(
                "UPDATE normative_versions "
                "SET name = :name, effective_date = :effective_date, "
                "rules_config = CAST(:rules_config AS JSON) "
                "WHERE id = :id"
            ),
            {
                "id": str(row["id"]),
                "name": _META["name"],
                "effective_date": _META["effective_date"],
                "rules_config": json.dumps(synced, ensure_ascii=False),
            },
        )

    op.drop_column("documents", "work_type")
    sa.Enum(name="worktype").drop(bind, checkfirst=True)


def downgrade() -> None:
    work_type_enum = sa.Enum("bachelor", "mas" + "ter", name="worktype")
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
