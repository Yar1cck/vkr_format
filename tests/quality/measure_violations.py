"""Замер качества обнаружения нарушений по типам (precision/recall/F1).

Эталон — `violation_annotations.json` со списком expected violations:
для каждой записи указано, должно ли алгоритм её найти (expected=true)
или это false positive из шаблона (expected=false). Записи с
expected=true и _detected=false — FN, добавленные вручную.

Match-стратегия: detected ↔ expected совпадает, если совпадает type И
paragraph_index в окне ±--paragraph-tolerance (по умолчанию ±2 абзаца).
Type-only matches (без paragraph_index) — для нарушений уровня документа
(volume_below_minimum, bibliography_missing и т.п.).

    python -m tests.quality.measure_violations \\
        --corpus tests/quality/corpus/ \\
        --annotations tests/quality/violation_annotations.json \\
        --output reports/violations_quality.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from services.core.vkr_core.config.normative_loader import load_default_rules
from services.core.vkr_core.engine import process_document

_DOC_LEVEL_TYPES = {
    "volume_below_minimum", "volume_above_maximum",
    "bibliography_missing", "bibliography_entries_autonumbered",
    "font_size_inconsistency",
}

# Типы, не участвующие в расчёте macro/micro F1.
# volume_below_minimum: синтетический корпус намеренно короче нормы —
# это не ошибка оформления, а артефакт тестового размера документа.
# paragraph_spacing: срабатывает на любом документе из python-docx с
# дефолтными стилями (SEVERITY_INFO, auto-fixed). Никогда не аннотируется
# как ожидаемое — поэтому всегда FP по метрике, что искажает картину.
_EXCLUDED_FROM_METRICS = {
    "volume_below_minimum",
    "volume_above_maximum",
    "paragraph_spacing",
}


@dataclass
class ExpectedViolation:
    type: str
    paragraph_index: int | None
    note: str | None = None


@dataclass
class DetectedViolation:
    type: str
    paragraph_index: int | None
    severity: str | None = None


@dataclass
class TypeCounts:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 0.0

    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 0.0

    def f1(self) -> float:
        p, r = self.precision(), self.recall()
        return 2 * p * r / (p + r) if (p + r) else 0.0


@dataclass
class DocEvaluation:
    filename: str
    detected_total: int
    expected_total: int
    matched: int
    fp_examples: list[str] = field(default_factory=list)
    fn_examples: list[str] = field(default_factory=list)


def _load_annotations(path: Path) -> dict[str, list[ExpectedViolation]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, list[ExpectedViolation]] = {}
    for doc in data.get("documents", []):
        filename = doc["filename"]
        expected: list[ExpectedViolation] = []
        for rec in doc.get("expected_violations", []):
            if rec.get("expected") is not True:
                continue
            expected.append(ExpectedViolation(
                type=rec["type"],
                paragraph_index=rec.get("paragraph_index"),
                note=rec.get("_note"),
            ))
        out[filename] = expected
    return out


def _detect(docx_path: Path, rules: dict) -> list[DetectedViolation]:
    result = process_document(docx_path, rules, check_only=True)
    return [
        DetectedViolation(type=v.type, paragraph_index=v.paragraph_index, severity=v.severity)
        for v in result.violations
    ]


def _match(
    detected: list[DetectedViolation],
    expected: list[ExpectedViolation],
    tolerance: int,
) -> tuple[list[tuple[DetectedViolation, ExpectedViolation]], list[DetectedViolation], list[ExpectedViolation]]:
    """Возвращает (matches, unmatched_detected, unmatched_expected).

    Жадная стратегия: для каждого expected выбираем первый detected того же type
    с paragraph_index в окне ±tolerance. Уже сматченные detected не используем.
    Document-level типы (см. _DOC_LEVEL_TYPES) матчатся без проверки индекса.
    """
    used_det = [False] * len(detected)
    matches: list[tuple[DetectedViolation, ExpectedViolation]] = []
    unmatched_exp: list[ExpectedViolation] = []

    for exp in expected:
        best_i = -1
        for i, det in enumerate(detected):
            if used_det[i] or det.type != exp.type:
                continue
            if exp.type in _DOC_LEVEL_TYPES or exp.paragraph_index is None or det.paragraph_index is None:
                best_i = i
                break
            if abs(det.paragraph_index - exp.paragraph_index) <= tolerance:
                best_i = i
                break
        if best_i == -1:
            unmatched_exp.append(exp)
        else:
            used_det[best_i] = True
            matches.append((detected[best_i], exp))

    unmatched_det = [d for d, used in zip(detected, used_det) if not used]
    return matches, unmatched_det, unmatched_exp


def _evaluate(
    docx_path: Path,
    rules: dict,
    expected: list[ExpectedViolation],
    tolerance: int,
) -> tuple[DocEvaluation, dict[str, TypeCounts]]:
    detected = _detect(docx_path, rules)
    matches, unmatched_det, unmatched_exp = _match(detected, expected, tolerance)

    per_type: dict[str, TypeCounts] = defaultdict(TypeCounts)
    for _, exp in matches:
        per_type[exp.type].tp += 1
    for det in unmatched_det:
        per_type[det.type].fp += 1
    for exp in unmatched_exp:
        per_type[exp.type].fn += 1

    ev = DocEvaluation(
        filename=docx_path.name,
        detected_total=len(detected),
        expected_total=len(expected),
        matched=len(matches),
        fp_examples=[f"{d.type}@{d.paragraph_index}" for d in unmatched_det[:10]],
        fn_examples=[f"{e.type}@{e.paragraph_index} ({e.note or ''})" for e in unmatched_exp[:10]],
    )
    return ev, per_type


def _merge_counts(dst: dict[str, TypeCounts], src: dict[str, TypeCounts]) -> None:
    for k, v in src.items():
        dst[k].tp += v.tp
        dst[k].fp += v.fp
        dst[k].fn += v.fn


def _summarize(per_type: dict[str, TypeCounts]) -> dict:
    types_report: dict[str, dict] = {}
    macro_f1 = []
    micro = TypeCounts()
    for t, c in sorted(per_type.items()):
        types_report[t] = {
            "tp": c.tp, "fp": c.fp, "fn": c.fn,
            "precision": round(c.precision(), 4),
            "recall": round(c.recall(), 4),
            "f1": round(c.f1(), 4),
            "excluded_from_metrics": t in _EXCLUDED_FROM_METRICS,
        }
        if t in _EXCLUDED_FROM_METRICS:
            continue
        if (c.tp + c.fp + c.fn) > 0:
            macro_f1.append(c.f1())
        micro.tp += c.tp
        micro.fp += c.fp
        micro.fn += c.fn

    return {
        "per_type": types_report,
        "macro_f1": round(sum(macro_f1) / len(macro_f1), 4) if macro_f1 else 0.0,
        "micro": {
            "tp": micro.tp, "fp": micro.fp, "fn": micro.fn,
            "precision": round(micro.precision(), 4),
            "recall": round(micro.recall(), 4),
            "f1": round(micro.f1(), 4),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Замер качества обнаружения нарушений")
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--annotations", required=True, type=Path,
                        help="JSON с разметкой (см. build_violation_annotations.py)")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--paragraph-tolerance", type=int, default=2,
                        help="Допустимая разница в paragraph_index при матче")
    args = parser.parse_args()

    if not args.corpus.is_dir():
        parser.error(f"Корпус не найден: {args.corpus}")
    if not args.annotations.is_file():
        parser.error(f"Разметка не найдена: {args.annotations}")

    rules = load_default_rules()
    annotations = _load_annotations(args.annotations)

    evaluations: list[DocEvaluation] = []
    aggregated: dict[str, TypeCounts] = defaultdict(TypeCounts)

    for docx_path in sorted(args.corpus.glob("*.docx")):
        expected = annotations.get(docx_path.name)
        if expected is None:
            print(f"  [skip] {docx_path.name}: нет разметки в {args.annotations.name}", file=sys.stderr)
            continue
        try:
            ev, per_type = _evaluate(docx_path, rules, expected, args.paragraph_tolerance)
        except Exception as exc:
            print(f"  [fail] {docx_path.name}: {exc}", file=sys.stderr)
            continue
        evaluations.append(ev)
        _merge_counts(aggregated, per_type)
        print(f"  [eval] {docx_path.name}: matched {ev.matched}/{ev.expected_total} "
              f"(detected {ev.detected_total})", file=sys.stderr)

    if not evaluations:
        print("Не удалось оценить ни одного документа", file=sys.stderr)
        return 2

    summary = _summarize(aggregated)
    report = {
        "documents_evaluated": len(evaluations),
        "paragraph_tolerance": args.paragraph_tolerance,
        **summary,
        "per_document": [
            {
                "filename": ev.filename,
                "detected_total": ev.detected_total,
                "expected_total": ev.expected_total,
                "matched": ev.matched,
                "fp_examples": ev.fp_examples,
                "fn_examples": ev.fn_examples,
            }
            for ev in evaluations
        ],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print(f"Отчёт сохранён в {args.output}")
    print(f"  documents:       {len(evaluations)}")
    print(f"  micro precision: {summary['micro']['precision']}")
    print(f"  micro recall:    {summary['micro']['recall']}")
    print(f"  micro F1:        {summary['micro']['f1']}")
    print(f"  macro F1:        {summary['macro_f1']}")
    print(f"  types covered:   {len(summary['per_type'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
