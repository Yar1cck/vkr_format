"""Русские названия типов замечаний для PDF/DOCX-отчёта.

ВНИМАНИЕ: зеркало frontend/src/utils/violationLabels.js (codebase'ы разные,
единый источник невозможен). При добавлении нового типа нарушения пополнять
ОБА файла.
"""
from __future__ import annotations

VIOLATION_TYPE_RU: dict[str, str] = {
    # Структура
    "missing_structural_section":        "Отсутствует обязательный раздел",
    "structural_order_violation":        "Нарушен порядок разделов",
    # Приложения
    "appendix_letter_invalid":           "Недопустимая буква приложения",
    "appendix_letter_gap":               "Пропуск в нумерации приложений",
    "appendix_not_referenced":           "Приложение не упомянуто в тексте",
    "appendix_order_violation":          "Порядок приложений нарушен",
    # Ссылки и источники
    "citation_sequence_issue":           "Нарушен порядок ссылок",
    "citation_without_source":           "Ссылка без источника в списке",
    "citation_separator_missing":        "Нет разделителя между ссылками",
    "citation_combined":                 "Несколько источников в одной скобке — разбито",
    "citation_range_suspicious":         "Подозрительный диапазон ссылок",
    "source_not_cited":                  "Источник не упомянут в тексте",
    "bibliography_missing":              "Список источников отсутствует",
    "bibliography_numbering_gap":        "Нарушена нумерация источников",
    "bibliography_entry_incomplete":     "Неполная запись источника",
    "bibliography_entry_malformed":      "Некорректный номер записи источника",
    "bibliography_entries_unrecognised": "Записи источников не распознаны",
    # Заголовки
    "forbidden_heading":                 "Недопустимый заголовок",
    "heading_rename":                    "Заголовок раздела приведён к канону",
    "heading_number_conflict":           "Конфликт нумерации заголовка",
    "heading_confirm":                   "Возможный заголовок — подтвердите",
    "possible_missed_heading":           "Возможный пропущенный заголовок",
    "heading_recovered":                 "Восстановлен пропущенный заголовок",
    # Рисунки/таблицы/формулы
    "figures_renumbered":                "Нумерация рисунков исправлена",
    "tables_renumbered":                 "Нумерация таблиц исправлена",
    "caption_renumbered":                "Нумерация подписи изменена",
    "figure_not_referenced":             "Рисунок без ссылки в тексте",
    "figure_reference_missing":          "Ссылка на несуществующий рисунок",
    "table_not_referenced":              "Таблица без ссылки в тексте",
    "table_reference_missing":           "Ссылка на несуществующую таблицу",
    "formula_without_explanation":       "Формула без пояснения символов",
    "formula_numbering_gap":             "Нарушена нумерация формул",
    # Объём и оформление
    "volume_below_minimum":              "Объём ниже допустимого",
    "volume_above_maximum":              "Объём превышает допустимый",
    "font_size_inconsistency":           "Разные размеры шрифта в тексте",
    "table_mass_bold_removed":           "Снято сплошное выделение в таблице",
    "long_table_split_warning":          "Длинная таблица разрезана для переноса",
    "paragraph_spacing":                 "Межстрочный интервал/отступы абзаца",
}


def violation_type_label(violation_type: str) -> str:
    """Русское название типа замечания. Никогда не возвращает английский id —
    неизвестный тип получает нейтральную русскую подпись."""
    return VIOLATION_TYPE_RU.get(violation_type, "Замечание оформления")
