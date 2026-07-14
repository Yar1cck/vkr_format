"""Обнаружение и оформление листингов кода (ТЗ §7.3, расширение).

Фрагмент кода в тексте — это подпись «Листинг N — <заголовок>» и идущий
сразу за ней блок строк кода. Делаем две вещи:

  L1. Перенумерация подписей «Листинг N» (сквозная/по главам по настройке),
      исходный заголовок сохраняется. Подпись стоит НАД кодом (как у
      таблиц), выравнивание — по левому краю.
  L2. Тело кода приводим к моноширинному виду: Courier New 10 pt, одинарный
      интервал, без абзацного отступа, по левому краю, без полужирного и
      без растяжения justify.

Блок кода ищем эвристически и консервативно (правило проекта — не ломать
содержательную часть): берём идущие сразу за подписью непустые абзацы,
пока они «похожи на код» (нумерованная строка «1.»/«1)» ИЛИ исходный
моноширинный шрифт). Первый абзац, не подходящий под эти признаки,
завершает блок.
"""

from __future__ import annotations

import re

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt

from services.core.vkr_core.engine.captions import _collect_captions
from services.core.vkr_core.engine.formatter import _strip_paragraph_outline_level

_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

_CODE_FONT = "Courier New"
_CODE_FONT_SIZE_PT = 10

# Моноширинные шрифты, по которым опознаём исходный блок кода.
_MONO_FONTS = {
    "courier new", "courier", "consolas", "cascadia code", "cascadia mono",
    "lucida console", "lucida sans typewriter", "monaco", "menlo",
    "dejavu sans mono", "liberation mono", "jetbrains mono", "fira code",
    "fira mono", "source code pro", "roboto mono", "ibm plex mono",
}

# Подпись листинга в начале абзаца. БЕЗ требования цифры: номер может быть
# приложенческим («Листинг А.1 — …») или вовсе отсутствовать — синхронно со
# стартовым паттерном captions._collect_captions(number_optional=True):
# `^Листинг\b`. Раньше здесь стояло `листинг\s+\d` (только цифра), из-за чего
# код в приложениях не распознавался и терял отступы (apply_body_style).
_LISTING_START_RE = re.compile(r"^\s*листинг\b", re.IGNORECASE)
# Строка кода, начинающаяся с порядкового номера: «1.», «12)», «3 ».
_NUMBERED_LINE_RE = re.compile(r"^\s*\d+\s*[.)\]]?\s")
_CODE_LIKE_RE = re.compile(
    r"^\s*(?:"
    r"def|class|import|from|return|if|elif|else|for|while|try|except|with|"
    r"const|let|var|function|public|private|protected|static|SELECT|INSERT|UPDATE|DELETE"
    r")\b|[{}]|\w+\s*\([^)]*\)",
    re.IGNORECASE,
)
# Строгий вариант для абзацев без моноширинного шрифта: только явные ключевые
# слова языков и фигурные скобки. =, <, >, ; и вызовы «слово(арг)» намеренно
# исключены — они слишком часто встречаются в формулах и обычном тексте.
_CODE_KEYWORD_RE = re.compile(
    r"^\s*(?:"
    r"def|class|import|from|return|if|elif|else|for|while|try|except|with|"
    r"const|let|var|function|public|private|protected|static|SELECT|INSERT|UPDATE|DELETE"
    r")\b|[{}]",
    re.IGNORECASE,
)


def _run_fonts(paragraph) -> set[str]:
    fonts: set[str] = set()
    for run in paragraph.runs:
        name = (run.font.name or "").strip().lower()
        if name:
            fonts.add(name)
    return fonts


def _is_code_line(paragraph) -> bool:
    """True, если абзац похож на строку кода листинга."""
    text = (paragraph.text or "").strip()
    if not text:
        return False
    if _LISTING_START_RE.match(text):
        return False  # это уже следующая подпись, а не код
    fonts = _run_fonts(paragraph)
    if fonts and fonts.issubset(_MONO_FONTS):
        # Моноширинный шрифт — необходимое, но не достаточное условие: абзац
        # после листинга может унаследовать Courier New от предыдущего абзаца
        # (Word проставляет его автоматически при нажатии Enter в коде).
        # Требуем дополнительно: ведущий пробел/таб (отступ кода), нумерацию
        # строки или совпадение с паттерном кода.
        raw = paragraph.text or ""
        if (raw and raw[0] in " \t") or _NUMBERED_LINE_RE.match(text) or _CODE_LIKE_RE.search(text):
            return True
        return False
    # Без моноширинного шрифта.
    # Нумерованная строка принимается только если содержимое после числа
    # выглядит как код (ключевое слово / {}). «1. Иванов И.И. …» не пройдёт.
    m = _NUMBERED_LINE_RE.match(text)
    if m:
        rest = text[m.end():]
        return bool(_CODE_KEYWORD_RE.search(rest))
    # =, <, > намеренно исключены из _CODE_KEYWORD_RE — часты в формулах.
    return bool(_CODE_KEYWORD_RE.search(text))


def _has_following_code_block(
    paragraphs,
    skip_indexes: set[int],
    caption_index: int,
) -> bool:
    """True, если первый непустой абзац после подписи выглядит как код."""
    j = caption_index + 1
    n = len(paragraphs)
    while j < n:
        if j in skip_indexes:
            return False
        pj = paragraphs[j]
        if not (pj.text or "").strip():
            j += 1
            continue
        return _is_code_line(pj)
    return False


def detect_listing_code_indexes(paragraphs, skip_indexes: set[int]) -> set[int]:
    """Индексы абзацев-строк кода (тело листингов).

    Нужны, чтобы исключить эти абзацы из apply_body_style — иначе их
    растянет justify и перебьёт шрифт на Times New Roman.
    """
    code: set[int] = set()
    n = len(paragraphs)
    idx = 0
    while idx < n:
        if idx in skip_indexes:
            idx += 1
            continue
        text = (paragraphs[idx].text or "").strip()
        if text and _LISTING_START_RE.match(text):
            if not _has_following_code_block(paragraphs, skip_indexes, idx):
                idx += 1
                continue
            j = idx + 1
            while j < n and j not in skip_indexes:
                pj = paragraphs[j]
                if not (pj.text or "").strip():
                    # Пустой абзац внутри блока пропускаем, но не включаем —
                    # apply_body_style его и так не трогает (нет stripped).
                    j += 1
                    continue
                if not _is_code_line(pj):
                    break
                code.add(j)
                j += 1
            idx = j
            continue
        idx += 1
    return code


def _apply_code_style(paragraph) -> None:
    """Тело листинга: меняем ТОЛЬКО шрифт.

    Отступы (left/first_line/right), табуляцию, выравнивание, межстрочный
    интервал и сам текст строк НЕ трогаем — у кода многоуровневая структура
    отступов, её нужно сохранить как в оригинале (требование заказчика).

    На каждый <w:t> ставим xml:space="preserve" — иначе LibreOffice при
    рендере отбрасывает ведущие пробелы строки, и отступы кода пропадают.
    """
    for run in paragraph.runs:
        run.font.name = _CODE_FONT
        run.font.size = Pt(_CODE_FONT_SIZE_PT)
        run.font.bold = False
        for t in run._r.findall(qn("w:t")):
            t.set(_XML_SPACE, "preserve")


def renumber_listings(
    paragraphs,
    skip_indexes: set[int],
    apply: bool,
    chapter_breaks: list[tuple[int, int]] | None = None,
):
    """Перенумеровывает подписи «Листинг N» и оформляет тело кода.

    Возвращает (listings, changes) — тот же контракт, что и
    captions.renumber_figures: changes — список (paragraph_index,
    original_text, new_text) с реально изменённым НОМЕРОМ.
    """
    # Шаг 1: черновые кандидаты.
    rough, _ = _collect_captions(
        paragraphs, skip_indexes, "Листинг", WD_ALIGN_PARAGRAPH.LEFT,
        "listing", False, number_optional=True, appendix_aware=True,
        chapter_breaks=chapter_breaks,
    )
    valid_caption_indexes = {
        cap.paragraph_index
        for cap in rough
        if _has_following_code_block(paragraphs, skip_indexes, cap.paragraph_index)
    }
    # Шаг 2: финальный прогон с отбраковкой ложных срабатываний
    # («Листинг N показывает ...» в прозе).
    filtered_skip_indexes = set(skip_indexes) | {
        cap.paragraph_index
        for cap in rough
        if cap.paragraph_index not in valid_caption_indexes
    }
    listings, changes = _collect_captions(
        paragraphs, filtered_skip_indexes, "Листинг", WD_ALIGN_PARAGRAPH.LEFT,
        "listing", apply, number_optional=True, appendix_aware=True,
        chapter_breaks=chapter_breaks,
    )

    if apply:
        n = len(paragraphs)
        for cap in listings:
            # Подпись листинга не должна попадать в Содержание. apply_body_style
            # уже снимает с неё outlineLvl, но подстрахуемся (шаблон мог нести
            # outlineLvl и на подписи, и на строках кода — а код мы исключаем
            # из apply_body_style, чтобы сохранить его отступы).
            if 0 <= cap.paragraph_index < n:
                _strip_paragraph_outline_level(paragraphs[cap.paragraph_index])
            j = cap.paragraph_index + 1
            while j < n and j not in skip_indexes:
                pj = paragraphs[j]
                if not (pj.text or "").strip():
                    j += 1
                    continue
                if not _is_code_line(pj):
                    break
                _strip_paragraph_outline_level(pj)
                _apply_code_style(pj)
                j += 1

    return listings, changes
