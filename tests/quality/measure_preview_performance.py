"""Замер времени генерации PDF-превью через LibreOffice.

Прогоняет каждый .docx из корпуса через convert_docx_to_pdf() дважды и
собирает медиану, p95, разброс по файлам. Требует установленного LibreOffice
(на macOS — /Applications/LibreOffice.app, в Docker — soffice в PATH).

    python3 -m tests.quality.measure_preview_performance \\
        --corpus /Users/yar/Desktop/test_folder \\
        --runs 2

Если LibreOffice не найден — завершается с понятной ошибкой.
"""

from __future__ import annotations

import argparse
import shutil
import statistics
import sys
import time
from pathlib import Path

from services.core.vkr_core.engine import instrumentation
from services.core.vkr_core.engine.preview import convert_docx_to_pdf
from services.core.vkr_core.utils.libreoffice import _find_soffice


def _check_soffice() -> str:
    binary = _find_soffice()
    if binary != "soffice" and Path(binary).exists():
        return binary
    if shutil.which("soffice"):
        return shutil.which("soffice")
    print(
        "❌  LibreOffice не найден.\n"
        "    macOS:  brew install --cask libreoffice\n"
        "    Linux:  apt-get install libreoffice\n"
        "    Docker: уже есть в образе Dockerfile.api\n",
        file=sys.stderr,
    )
    sys.exit(1)


def _measure_one(path: Path) -> dict:
    """Одна конвертация с инструментацией. Возвращает словарь с метриками."""
    instrumentation.enable_timing()
    instrumentation.reset()

    t0 = time.perf_counter()
    try:
        pdf = convert_docx_to_pdf(path, fast=False)
        total_s = time.perf_counter() - t0
        size_kb = pdf.stat().st_size // 1024
        pdf.unlink(missing_ok=True)
        pdf.parent.rmdir()
    except Exception as exc:
        return {"error": str(exc), "total_s": time.perf_counter() - t0}

    steps = {r.step: r.duration_ms for r in instrumentation.collector().records}
    return {
        "total_s": total_s,
        "size_kb": size_kb,
        "preview_soffice_ms": steps.get("preview_soffice", 0),
        "preview_unoconvert_ms": steps.get("preview_unoconvert", 0),
    }


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sv = sorted(values)
    k = (len(sv) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(sv) - 1)
    return sv[lo] + (sv[hi] - sv[lo]) * (k - lo)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default="tests/quality/corpus", help="Директория с .docx")
    parser.add_argument("--runs", type=int, default=2, help="Прогонов на файл")
    args = parser.parse_args()

    soffice_bin = _check_soffice()
    print(f"✓  LibreOffice: {soffice_bin}\n")

    corpus = Path(args.corpus)
    docx_files = sorted(corpus.glob("*.docx"))
    if not docx_files:
        print(f"Нет .docx в {corpus}", file=sys.stderr)
        sys.exit(1)

    print(f"Корпус: {len(docx_files)} файлов, {args.runs} прогона(ов) каждый\n")
    print(f"{'Файл':<55} {'мин,с':>6} {'мед,с':>6} {'макс,с':>7} {'p95,с':>6} {'КБ':>6}")
    print("─" * 90)

    all_totals: list[float] = []
    all_soffice: list[float] = []

    for docx in docx_files:
        samples: list[float] = []
        soffice_samples: list[float] = []
        size_kb = 0
        for _ in range(args.runs):
            r = _measure_one(docx)
            if "error" in r:
                print(f"  ERROR {docx.name}: {r['error']}")
                break
            samples.append(r["total_s"])
            if r["preview_soffice_ms"]:
                soffice_samples.append(r["preview_soffice_ms"] / 1000)
            size_kb = r.get("size_kb", 0)

        if not samples:
            continue

        med = statistics.median(samples)
        all_totals.extend(samples)
        all_soffice.extend(soffice_samples)

        name = docx.name[:54]
        print(
            f"{name:<55} {min(samples):>6.2f} {med:>6.2f} {max(samples):>7.2f}"
            f" {_pct(samples, 95):>6.2f} {size_kb:>6}"
        )

    if not all_totals:
        print("Нет результатов.")
        return

    print("─" * 90)
    print(f"\n📊  Сводка ({len(all_totals)} измерений, {len(docx_files)} файлов):")
    print(f"    Общее время (total)   — медиана: {statistics.median(all_totals):.2f} с"
          f"  p95: {_pct(all_totals, 95):.2f} с"
          f"  min: {min(all_totals):.2f} с"
          f"  max: {max(all_totals):.2f} с")
    if all_soffice:
        print(f"    soffice (LO startup)  — медиана: {statistics.median(all_soffice):.2f} с"
              f"  p95: {_pct(all_soffice, 95):.2f} с")


if __name__ == "__main__":
    main()
