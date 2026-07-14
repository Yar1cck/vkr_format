"""Замер производительности pipeline на корпусе .docx.

Каждый файл прогоняется N раз (по умолчанию 3) — берём медиану и p95.
Для каждого файла даём по шагам конвейера и итог. Включает timing
автоматически (enable_timing) — не зависит от env-переменной.

    python -m tests.quality.measure_pipeline_performance \\
        --corpus tests/quality/corpus/ \\
        --output reports/performance.json \\
        --runs 3 --mode check
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

from services.core.vkr_core.config.normative_loader import load_default_rules
from services.core.vkr_core.engine import instrumentation, process_document


def _measure_one(docx_path: Path, rules: dict, check_only: bool) -> tuple[float, dict[str, float]]:
    """Возвращает (total_seconds, {step: ms_total_for_steps_in_this_run})."""
    instrumentation.enable_timing()
    instrumentation.reset()

    t0 = time.perf_counter()
    process_document(docx_path, rules, check_only=check_only)
    total_s = time.perf_counter() - t0

    by_step: dict[str, float] = defaultdict(float)
    for rec in instrumentation.collector().records:
        by_step[rec.step] += rec.duration_ms

    return total_s, dict(by_step)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    sorted_v = sorted(values)
    k = (len(sorted_v) - 1) * pct / 100.0
    f = int(k)
    c = min(f + 1, len(sorted_v) - 1)
    if f == c:
        return sorted_v[f]
    return sorted_v[f] + (sorted_v[c] - sorted_v[f]) * (k - f)


def _aggregate(samples: list[float]) -> dict:
    if not samples:
        return {"runs": 0}
    return {
        "runs": len(samples),
        "min": round(min(samples), 4),
        "max": round(max(samples), 4),
        "median": round(statistics.median(samples), 4),
        "mean": round(statistics.fmean(samples), 4),
        "p95": round(_percentile(samples, 95), 4),
    }


def _measure_corpus(
    corpus: Path,
    rules: dict,
    check_only: bool,
    runs: int,
    warmup: int,
) -> dict:
    per_file: list[dict] = []

    for docx_path in sorted(corpus.glob("*.docx")):
        print(f"  [run] {docx_path.name}: warmup={warmup}, runs={runs}", file=sys.stderr)

        for _ in range(warmup):
            try:
                _measure_one(docx_path, rules, check_only)
            except Exception as exc:
                print(f"    [warmup-fail] {exc}", file=sys.stderr)

        total_samples: list[float] = []
        step_samples: dict[str, list[float]] = defaultdict(list)

        for i in range(runs):
            try:
                total_s, by_step = _measure_one(docx_path, rules, check_only)
            except Exception as exc:
                print(f"    [run{i}-fail] {exc}", file=sys.stderr)
                continue
            total_samples.append(total_s)
            for step, ms in by_step.items():
                step_samples[step].append(ms)

        if not total_samples:
            print(f"    [skip] {docx_path.name}: ни один прогон не выжил", file=sys.stderr)
            continue

        per_file.append({
            "filename": docx_path.name,
            "size_bytes": docx_path.stat().st_size,
            "total_seconds": _aggregate(total_samples),
            "by_step_ms": {step: _aggregate(s) for step, s in step_samples.items()},
        })

        print(f"    median={_aggregate(total_samples)['median']}s", file=sys.stderr)

    aggregated_steps: dict[str, list[float]] = defaultdict(list)
    aggregated_totals: list[float] = []
    for entry in per_file:
        aggregated_totals.append(entry["total_seconds"]["median"])
        for step, agg in entry["by_step_ms"].items():
            aggregated_steps[step].append(agg["median"])

    return {
        "mode": "check_only" if check_only else "full",
        "documents_evaluated": len(per_file),
        "total_seconds_across_corpus": _aggregate(aggregated_totals),
        "by_step_ms_across_corpus": {step: _aggregate(s) for step, s in aggregated_steps.items()},
        "per_document": per_file,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Замер производительности pipeline")
    parser.add_argument("--corpus", required=True, type=Path,
                        help="Каталог с .docx")
    parser.add_argument("--output", required=True, type=Path,
                        help="Куда сохранить отчёт JSON")
    parser.add_argument("--runs", type=int, default=3, help="Число замеряемых прогонов на файл")
    parser.add_argument("--warmup", type=int, default=1, help="Число «прогревочных» прогонов")
    parser.add_argument("--mode", choices=["check", "full", "both"], default="check",
                        help="Какой режим pipeline замеряем")
    args = parser.parse_args()

    if not args.corpus.is_dir():
        parser.error(f"Корпус не найден: {args.corpus}")

    rules = load_default_rules()
    report: dict = {}

    if args.mode in ("check", "both"):
        print("=== mode=check_only ===", file=sys.stderr)
        report["check_only"] = _measure_corpus(args.corpus, rules, True, args.runs, args.warmup)
    if args.mode in ("full", "both"):
        print("=== mode=full ===", file=sys.stderr)
        report["full"] = _measure_corpus(args.corpus, rules, False, args.runs, args.warmup)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nОтчёт сохранён в {args.output}")

    for mode, data in report.items():
        agg = data.get("total_seconds_across_corpus", {})
        print(f"  [{mode}] documents={data['documents_evaluated']}, "
              f"median={agg.get('median', 0)}s, p95={agg.get('p95', 0)}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
