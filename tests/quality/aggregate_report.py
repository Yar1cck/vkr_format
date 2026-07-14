"""Сводный отчёт качества: объединяет 4 JSON-отчёта в один summary с печатной таблицей.

    python -m tests.quality.aggregate_report --reports reports/ --output reports/quality_summary.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"  [warn] не смог прочитать {path}: {exc}", file=sys.stderr)
        return None


def _summarize_coverage(cov: dict | None) -> dict:
    if not cov:
        return {"available": False}
    totals = cov.get("totals", {})
    return {
        "available": True,
        "percent_covered": round(totals.get("percent_covered", 0.0), 2),
        "percent_covered_display": totals.get("percent_covered_display"),
        "num_statements": totals.get("num_statements"),
        "missing_lines": totals.get("missing_lines"),
        "covered_lines": totals.get("covered_lines"),
    }


def _summarize_heading(h: dict | None) -> dict:
    if not h:
        return {"available": False}
    binary = h.get("binary", {})
    level = h.get("level", {})
    return {
        "available": True,
        "documents_evaluated": h.get("documents_evaluated"),
        "precision": binary.get("precision"),
        "recall": binary.get("recall"),
        "f1": binary.get("f1"),
        "level_accuracy": level.get("accuracy"),
    }


def _summarize_violations(v: dict | None) -> dict:
    if not v:
        return {"available": False}
    micro = v.get("micro", {})
    return {
        "available": True,
        "documents_evaluated": v.get("documents_evaluated"),
        "types_covered": len(v.get("per_type", {})),
        "micro_precision": micro.get("precision"),
        "micro_recall": micro.get("recall"),
        "micro_f1": micro.get("f1"),
        "macro_f1": v.get("macro_f1"),
        "top_weakest_types": _top_weakest(v.get("per_type", {}), n=5),
    }


def _top_weakest(per_type: dict, n: int = 5) -> list[dict]:
    items = [
        {
            "type": t,
            "f1": d.get("f1", 0.0),
            "tp": d.get("tp"), "fp": d.get("fp"), "fn": d.get("fn"),
        }
        for t, d in per_type.items()
        if (d.get("tp", 0) + d.get("fp", 0) + d.get("fn", 0)) > 0
    ]
    return sorted(items, key=lambda x: x["f1"])[:n]


def _summarize_perf(p: dict | None) -> dict:
    if not p:
        return {"available": False}
    out: dict = {"available": True, "modes": {}}
    for mode_key in ("check_only", "full"):
        if mode_key not in p:
            continue
        mode = p[mode_key]
        agg = mode.get("total_seconds_across_corpus", {})
        steps = mode.get("by_step_ms_across_corpus", {})
        slowest = sorted(steps.items(), key=lambda kv: -kv[1].get("median", 0))[:5]
        out["modes"][mode_key] = {
            "documents_evaluated": mode.get("documents_evaluated"),
            "median_seconds": agg.get("median"),
            "p95_seconds": agg.get("p95"),
            "slowest_steps_ms": [
                {"step": s, "median": st.get("median"), "p95": st.get("p95")}
                for s, st in slowest
            ],
        }
    return out


def _print_table(summary: dict) -> None:
    print()
    print("=" * 70)
    print(" Сводный отчёт качества VKR.Format")
    print("=" * 70)

    cov = summary["coverage"]
    if cov["available"]:
        print(f"\n[Покрытие] engine/: {cov['percent_covered_display']}%  "
              f"({cov['covered_lines']}/{cov['num_statements']} строк)")
    else:
        print("\n[Покрытие] нет данных (reports/coverage.json не найден)")

    h = summary["heading_detection"]
    if h["available"]:
        print(f"\n[Детектор заголовков] precision={h['precision']}  recall={h['recall']}  F1={h['f1']}")
        print(f"  Точность уровня (L1/L2/L3): {h['level_accuracy']}  "
              f"на {h['documents_evaluated']} док.")
    else:
        print("\n[Детектор заголовков] нет данных")

    v = summary["violations"]
    if v["available"]:
        print(f"\n[Нарушения] micro: precision={v['micro_precision']}  "
              f"recall={v['micro_recall']}  F1={v['micro_f1']}")
        print(f"  macro F1={v['macro_f1']}  на {v['documents_evaluated']} док., "
              f"{v['types_covered']} типов")
        if v["top_weakest_types"]:
            print("  Слабые типы (по F1):")
            for w in v["top_weakest_types"]:
                print(f"    {w['type']:40s} F1={w['f1']:.3f}  tp={w['tp']} fp={w['fp']} fn={w['fn']}")
    else:
        print("\n[Нарушения] нет данных")

    p = summary["performance"]
    if p["available"]:
        for mode, data in p["modes"].items():
            print(f"\n[Производительность / {mode}] median={data['median_seconds']}s  "
                  f"p95={data['p95_seconds']}s  на {data['documents_evaluated']} док.")
            for s in data["slowest_steps_ms"]:
                print(f"    {s['step']:40s} median={s['median']:.1f}ms  p95={s['p95']:.1f}ms")
    else:
        print("\n[Производительность] нет данных")

    print()
    print("=" * 70)


def main() -> int:
    parser = argparse.ArgumentParser(description="Сводный отчёт качества")
    parser.add_argument("--reports", required=True, type=Path,
                        help="Папка с JSON-отчётами (coverage/heading_quality/violations_quality/performance)")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    coverage = _load(args.reports / "coverage.json")
    heading = _load(args.reports / "heading_quality.json")
    violations = _load(args.reports / "violations_quality.json")
    performance = _load(args.reports / "performance.json")

    summary = {
        "coverage": _summarize_coverage(coverage),
        "heading_detection": _summarize_heading(heading),
        "violations": _summarize_violations(violations),
        "performance": _summarize_perf(performance),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _print_table(summary)
    print(f"\nСводка сохранена в {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
