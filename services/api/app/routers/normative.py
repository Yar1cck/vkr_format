from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.dependencies import get_current_user
from services.core.vkr_core.db.session import get_db
from services.core.vkr_core.models import User
from services.core.vkr_core.schemas import NormativeRulesOut, NormativeVersionOut
from services.core.vkr_core.services import get_normative_by_id, list_normative_versions

router = APIRouter(prefix="/api/v1/normative", tags=["normative"])

_DOCS_DIR = Path(__file__).parents[4] / "docs" / "normative"

# Человекочитаемые имена для файлов. Ключ — stem PDF-файла.
_SLUG_MAP: dict[str, tuple[str, str]] = {
    "prikaz_697-1_29.12.2023": ("prikaz-697-1", "Приказ МИИГАиК №697-01 от 29.12.2023"),
    "gost_7.32-2017":          ("gost-7-32-2017", "ГОСТ 7.32-2017 — Отчёт о научно-исследовательской работе"),
}


@router.get("/reference-docs", summary="Список справочных нормативных документов")
async def list_reference_docs() -> list[dict]:
    """Возвращает список PDF-справочников из docs/normative/.
    Авторизация не требуется — документы публичны.
    При добавлении нового PDF в docs/normative/ он автоматически появится в списке."""
    docs = []
    for pdf in sorted(_DOCS_DIR.glob("*.pdf")):
        slug, name = _SLUG_MAP.get(pdf.stem, (pdf.stem, pdf.stem))
        docs.append({"slug": slug, "name": name, "url": f"/api/v1/normative/reference-docs/{slug}"})
    return docs


@router.get("/reference-docs/{slug}", summary="Открыть справочный документ inline")
async def get_reference_doc(slug: str) -> FileResponse:
    """Отдаёт PDF нормативного документа для просмотра в браузере (Content-Disposition: inline).
    Авторизация не требуется."""
    reverse = {v[0]: stem for stem, v in _SLUG_MAP.items()}
    stem = reverse.get(slug, slug)
    path = _DOCS_DIR / f"{stem}.pdf"
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Документ не найден")
    return FileResponse(
        path,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline"},
    )


@router.get("/versions", response_model=list[NormativeVersionOut], summary="Список версий нормативной базы")
async def get_versions(
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[NormativeVersionOut]:
    """Все версии нормативной базы МИИГАиК. Активная помечена is_active=true."""
    versions = await list_normative_versions(db)
    return [NormativeVersionOut.model_validate(v) for v in versions]


@router.get("/{version_id}/rules", response_model=NormativeRulesOut, summary="Правила нормативной версии")
async def get_rules(
    version_id: UUID,
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NormativeRulesOut:
    """Полный JSON правил оформления (page_settings, body_text_style,
    forbidden_heading_map, structural_elements и пр.). Read-only;
    редактирование — `PUT /admin/normative/{id}/rules`."""
    version = await get_normative_by_id(version_id, db)
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Normative version not found")
    return NormativeRulesOut(version_id=version.id, rules_config=version.rules_config)
