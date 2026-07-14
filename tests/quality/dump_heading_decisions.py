"""Debug-инструмент: таблица решений детектора заголовков по каждому абзацу.

Запуск:
    python -m tests.quality.dump_heading_decisions path/to/file.docx
    python -m tests.quality.dump_heading_decisions path/to/file.docx --rejected
    python -m tests.quality.dump_heading_decisions path/to/file.docx --all

Режимы:
    (по умолчанию) — только принятые заголовки (HIGH + MEDIUM + LOW-recovered)
    --rejected      — только отклонённые (hard-reject + NONE tier)
    --all           — все абзацы; строки с tier=NONE серые, rejected — с пометкой
    --min-score N   — показывать только абзацы с score >= N (работает с --all / --rejected)
    --search TEXT   — фильтровать по тексту абзаца (case-insensitive)
    --csv           — выводить в CSV вместо таблицы
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from docx import Document as WordDocument

from services.core.vkr_core.config.normative_loader import load_default_rules
from services.core.vkr_core.engine.detection import detect_headings_full
from services.core.vkr_core.engine.heading_hierarchy import apply_hierarchy
from services.core.vkr_core.engine.heading_scoring import (
    TIER_HIGH,
    TIER_LOW,
    TIER_MEDIUM,
    TIER_NONE,
    score_paragraph,
)
from services.core.vkr_core.engine.stats import collect_stats
from services.core.vkr_core.engine.title_page import detect_title_page_end
from services.core.vkr_core.engine.toc import detect_toc_section_indexes

_TIER_COLOR = {
    TIER_HIGH:   "\033[92m",  # зелёный
    TIER_MEDIUM: "\033[93m",  # жёлтый
    TIER_LOW:    "\033[96m",  # голубой
    TIER_NONE:   "\033[90m",  # серый
    "rejected":  "\033[91m",  # красный
    "recovered": "\033[94m",  # синий
}
_RESET = "\033[0m"


def _trunc(text: str, n: int = 60) -> str:
    return text[:n - 1] + "…" if len(text) > n else text


def _tier_label(tier: str, score: int, hard_reject: str | None) -> str:
    if hard_reject:
        return f"REJECT({hard_reject})"
    return f"{tier.upper()}({score})"


def run(docx_path: Path, args: argparse.Namespace) -> None:
    doc = WordDocument(str(docx_path))
    rules = load_default_rules()
    stats = collect_stats(doc)

    title_end = detect_title_page_end(stats, rules)
    title_page_indexes = set(range(title_end))
    toc_indexes = detect_toc_section_indexes(doc, rules)
    skip = title_page_indexes | toc_indexes

    # Прогоняем full detection, чтобы знать, какие LOW были приняты (recovered)
    candidates, soft_violations = detect_headings_full(stats, rules, skip)
    accepted_indexes = {c.paragraph_index for c in candidates}
    recovered_indexes = {
        v.paragraph_index
        for v in soft_violations
        if v.type == "heading_recovered"
    }

    # Собираем сырые скоры всех абзацев (включая rejected)
    rows: list[dict] = []
    for ps in stats.paragraphs:
        score = score_paragraph(ps, stats, rules, skip)

        # Определяем итоговый статус строки
        if score.hard_reject_reason:
            status = "rejected"
            tier_display = f"REJECT({score.hard_reject_reason})"
        elif score.index in recovered_indexes:
            status = "recovered"
            tier_display = f"RECOV({score.score})"
        elif score.index in accepted_indexes:
            status = score.tier
            tier_display = f"{score.tier.upper()}({score.score})"
        elif score.tier == TIER_NONE:
            status = TIER_NONE
            tier_display = f"NONE({score.score})"
        else:
            # LOW или MEDIUM, не принятые (не recovered, не в candidates)
            status = score.tier
            tier_display = f"{score.tier.upper()}({score.score})-soft"

        rows.append({
            "idx": ps.index,
            "status": status,
            "tier_display": tier_display,
            "score": score.score,
            "level": score.level if not score.hard_reject_reason else "-",
            "text": ps.stripped,
            "signals": ", ".join(score.signals) if score.signals else (score.hard_reject_reason or ""),
        })

    # Фильтрация
    search = args.search.lower() if args.search else None
    if search:
        rows = [r for r in rows if search in r["text"].lower()]

    if args.all:
        filtered = rows
    elif args.rejected:
        filtered = [r for r in rows if r["status"] == "rejected"]
        if args.min_score is not None:
            filtered = [r for r in filtered if r["score"] >= args.min_score]
    else:
        # По умолчанию — только принятые заголовки
        accepted_statuses = {TIER_HIGH, TIER_MEDIUM, TIER_LOW, "recovered"}
        filtered = [r for r in rows if r["status"] in accepted_statuses]

    if args.min_score is not None and args.all:
        filtered = [r for r in filtered if r["score"] >= args.min_score]

    if not filtered:
        print("Нет строк для отображения (попробуйте --all или --rejected).")
        return

    if args.csv:
        _print_csv(filtered)
    else:
        _print_table(filtered, use_color=sys.stdout.isatty())


def _print_table(rows: list[dict], use_color: bool) -> None:
    col_idx  = 5
    col_tier = 18
    col_lvl  = 3
    col_text = 58
    col_sig  = 55

    header = (
        f"{'idx':>{col_idx}}  "
        f"{'tier':<{col_tier}}  "
        f"{'lvl':>{col_lvl}}  "
        f"{'text':<{col_text}}  "
        f"signals"
    )
    sep = "-" * (col_idx + 2 + col_tier + 2 + col_lvl + 2 + col_text + 2 + col_sig)
    print(header)
    print(sep)

    for r in rows:
        status = r["status"]
        color = _TIER_COLOR.get(status, "") if use_color else ""
        reset = _RESET if use_color else ""

        tier_str = f"{r['tier_display']:<{col_tier}}"
        text_str = f"{_trunc(r['text'], col_text):<{col_text}}"
        sig_str  = _trunc(r["signals"], col_sig)

        print(
            f"{color}"
            f"{r['idx']:>{col_idx}}  "
            f"{tier_str}  "
            f"{str(r['level']):>{col_lvl}}  "
            f"{text_str}  "
            f"{sig_str}"
            f"{reset}"
        )


def _print_csv(rows: list[dict]) -> None:
    writer = csv.DictWriter(
        sys.stdout,
        fieldnames=["idx", "tier_display", "score", "level", "text", "signals"],
        extrasaction="ignore",
    )
    writer.writeheader()
    writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Таблица решений детектора заголовков по каждому абзацу"
    )
    parser.add_argument("docx", type=Path, help="Путь к .docx файлу")
    parser.add_argument("--all", action="store_true", help="Показать все абзацы")
    parser.add_argument("--rejected", action="store_true", help="Показать только отклонённые")
    parser.add_argument("--min-score", type=int, metavar="N", dest="min_score",
                        help="Минимальный score для отображения")
    parser.add_argument("--search", metavar="TEXT",
                        help="Фильтр по тексту абзаца (case-insensitive)")
    parser.add_argument("--csv", action="store_true", help="Вывод в CSV")
    args = parser.parse_args()

    if not args.docx.exists():
        print(f"Файл не найден: {args.docx}", file=sys.stderr)
        return 1

    run(args.docx, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
