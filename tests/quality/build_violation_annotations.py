"""Помощник разметки нарушений на корпусе.

Прогоняет `process_document(check_only=True)` на каждом .docx и выгружает
все найденные violations в шаблон JSON. Размечающий вручную проставляет
поле `expected` для каждой записи: true (TP — это настоящее нарушение)
или false (FP — алгоритм соврал). Записи о нарушениях, которые в файле
есть, но алгоритм пропустил (FN), добавляются вручную с `expected: true`
и `_detected: false`.

Формат итогового файла:

    {
      "_format_version": 1,
      "documents": [
        {
          "filename": "ivanov_vkr.docx",
          "expected_violations": [
            {
              "type": "forbidden_heading",
              "paragraph_index": 42,
              "expected": true,
              "_detected": true,
              "_note": "ОГЛАВЛЕНИЕ вместо СОДЕРЖАНИЕ — настоящая ошибка"
            },
            {
              "type": "citation_separator_missing",
              "paragraph_index": 156,
              "expected": false,
              "_detected": true,
              "_note": "FP: это не ссылки, а математические скобки"
            },
            {
              "type": "appendix_letter_gap",
              "expected": true,
              "_detected": false,
              "_note": "FN: алгоритм должен был это найти"
            }
          ]
        }
      ]
    }

Запуск:
    python -m tests.quality.build_violation_annotations \\
        --corpus tests/quality/corpus/ \\
        --output tests/quality/violation_annotations.draft.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from services.core.vkr_core.config.normative_loader import load_default_rules
from services.core.vkr_core.engine import process_document


def _violation_record(v) -> dict:
    rec = {
        "type": v.type,
        "expected": None,
        "_detected": True,
    }
    if v.paragraph_index is not None:
        rec["paragraph_index"] = v.paragraph_index
    if v.severity:
        rec["_severity"] = v.severity
    if v.rule_reference:
        rec["_rule"] = v.rule_reference
    if v.section_title:
        rec["_note"] = f"section={v.section_title[:60]}"
    elif v.original_text:
        rec["_note"] = f"text={v.original_text[:60]}"
    return rec


def main() -> int:
    parser = argparse.ArgumentParser(description="Шаблон разметки violations для корпуса")
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    if not args.corpus.is_dir():
        parser.error(f"Корпус не найден: {args.corpus}")

    rules = load_default_rules()
    documents = []

    for docx_path in sorted(args.corpus.glob("*.docx")):
        try:
            result = process_document(docx_path, rules, check_only=True)
        except Exception as exc:
            print(f"  [fail] {docx_path.name}: {exc}", file=sys.stderr)
            continue

        records = [_violation_record(v) for v in result.violations]
        documents.append({
            "filename": docx_path.name,
            "_volume_pages": result.volume_pages,
            "_detected_count": len(records),
            "expected_violations": records,
        })
        print(f"  {docx_path.name}: {len(records)} нарушений в шаблоне", file=sys.stderr)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_format_version": 1,
        "_documentation": [
            "Для каждой записи проставьте expected: true (TP) или false (FP).",
            "Если алгоритм пропустил настоящее нарушение, добавьте запись",
            "с expected=true и _detected=false (FN). Тогда measure_violations",
            "учтёт её в recall.",
        ],
        "documents": documents,
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nШаблон сохранён в {args.output} ({len(documents)} документов)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
