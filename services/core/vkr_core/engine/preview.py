"""Генерирует PDF-превью, точно соответствующие виду в Word, через
LibreOffice headless."""

from __future__ import annotations

import tempfile
from pathlib import Path

from services.core.vkr_core.engine import instrumentation
from services.core.vkr_core.utils.libreoffice import convert_via_unoconvert, run_soffice

# Быстрый PDF-экспорт для ИЗМЕРИТЕЛЬНЫХ рендеров: низкий DPI/качество
# картинок и сжатие. Раскладка (разбивка на страницы, позиции строк,
# колонтитулы) от этого НЕ меняется — она зависит от размеров картинок в
# документе, а не от их растрового качества. pdftotext читает только текст
# и form-feed границы страниц. Поэтому измерение остаётся точным, а рендер
# заметно быстрее. Для финального превью fast НЕ используем (полное качество).
_FAST_PDF_FILTER = (
    'pdf:writer_pdf_Export:{'
    '"ReduceImageResolution":{"type":"boolean","value":true},'
    '"MaxImageResolution":{"type":"long","value":75},'
    '"Quality":{"type":"long","value":25},'
    '"UseLosslessCompression":{"type":"boolean","value":false},'
    '"ExportBookmarks":{"type":"boolean","value":false}'
    '}'
)


def convert_multiple_docx_to_pdf(
    docx_paths: list[Path], timeout: int = 180
) -> list[Path | None]:
    """Конвертирует несколько .docx в PDF.

    При наличии unoserver: каждый файл через unoconvert (нет стартапа LO).
    Иначе: один запуск soffice для всего пакета (один стартап на N файлов).
    Возвращает список результатов в том же порядке; None — если PDF не создан.
    """
    if not docx_paths:
        return []
    outdir = Path(tempfile.mkdtemp(prefix="vkr-pdf-"))

    # Путь 1: unoserver тёплый — конвертируем без стартапа LO.
    uno_results: list[Path | None] = []
    all_ok = True
    for p in docx_paths:
        out = outdir / (p.stem + ".pdf")
        if convert_via_unoconvert(p, out, timeout=min(timeout, 90)):
            uno_results.append(out)
        else:
            all_ok = False
            break
    if all_ok and uno_results:
        return uno_results

    # Путь 2: один soffice для всего пакета (один старт LO на N файлов).
    proc = run_soffice([
        "--convert-to", "pdf",
        "--outdir", str(outdir),
        *[str(p) for p in docx_paths],
    ], timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(
            f"LibreOffice batch convert failed (exit {proc.returncode}): "
            f"{proc.stderr.decode(errors='replace').strip()[:300]}"
        )
    results: list[Path | None] = []
    for p in docx_paths:
        candidate = outdir / (p.stem + ".pdf")
        results.append(candidate if candidate.exists() else None)
    return results


def convert_docx_to_pdf(
    docx_path: Path, timeout: int = 180, fast: bool = False
) -> Path:
    """Рендерит .docx в .pdf, постраничная разбивка которого близка к Word.

    fast=True — быстрый низкокачественный экспорт для ИЗМЕРИТЕЛЬНЫХ рендеров
    (раскладка/текст/колонтитулы идентичны, меняется только качество
    картинок). Для финального превью использовать fast=False.

    Возвращает путь к созданному PDF (во временной директории — за её
    удаление при необходимости отвечает вызывающая сторона).
    """
    outdir = Path(tempfile.mkdtemp(prefix="vkr-pdf-"))

    # Финальный рендер: пробуем unoserver (нет стартапа LO ≈ −3–5 с).
    # fast-рендеры используют нестандартный фильтр — unoconvert его не знает,
    # поэтому для них всегда идём через run_soffice.
    if not fast:
        out = outdir / (docx_path.stem + ".pdf")
        with instrumentation.timed("preview_unoconvert"):
            ok = convert_via_unoconvert(docx_path, out, timeout=min(timeout, 90))
        if ok:
            return out

    with instrumentation.timed("preview_soffice"):
        proc = run_soffice([
            "--convert-to",
            _FAST_PDF_FILTER if fast else "pdf",
            "--outdir",
            str(outdir),
            str(docx_path),
        ], timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(
            f"LibreOffice did not produce PDF (exit {proc.returncode}): "
            f"{proc.stderr.decode(errors='replace').strip()[:300]}"
        )
    produced = list(outdir.glob("*.pdf"))
    if not produced:
        raise RuntimeError("LibreOffice did not produce PDF")
    return produced[0]
