"""Обнаружение, проверка и перенумерация подписей рисунков и таблиц (ТЗ §7.3).

Правила:
  C1. Подписи рисунков: "Рисунок N — <Заголовок>" (по центру).
      Подписи таблиц:  "Таблица N — <Заголовок>" (слева, над таблицей,
      без абзацного отступа — Порядок МИИГАиК п.6.13 / ГОСТ 7.32 §6.6.3).
      N — по настройке: сквозная или по главам.
  C2. На каждую подпись в тексте должна быть хотя бы одна ссылка вида
      "рис. N" / "см. рисунок N" / "табл. N". Если ссылок нет — выдаём
      предупреждение.
  C3. Перенумерация работает только в режиме "full"; исходный заголовок
      подписи сохраняется.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from services.core.vkr_core.engine.formatter import overwrite_paragraph_text
from services.core.vkr_core.engine.stats import DocStats
from services.core.vkr_core.engine.violations import (
    SEVERITY_INFO,
    SEVERITY_WARNING,
    PipelineViolation,
)
from services.core.vkr_core.models.enums import ViolationStatus

_CAPTION_FONT = "Times New Roman"
_CAPTION_FONT_SIZE_PT = 14


def _set_caption_font(paragraph) -> None:
    for run in paragraph.runs:
        run.font.name = _CAPTION_FONT
        run.font.size = Pt(_CAPTION_FONT_SIZE_PT)
        run.font.bold = False
        run.font.italic = False


def _apply_caption_indent(paragraph, indent_cm: float) -> None:
    """Устанавливает first_line_indent на абзаце подписи, предварительно
    очищая конфликтующие атрибуты w:left / w:hanging / w:start из w:ind,
    чтобы шаблонный отступ не перебивал наш first-line indent."""
    pPr = paragraph._p.find(qn("w:pPr"))
    if pPr is None:
        from docx.oxml import OxmlElement
        pPr = OxmlElement("w:pPr")
        paragraph._p.insert(0, pPr)
    ind = pPr.find(qn("w:ind"))
    if ind is not None:
        for attr in (
            "w:left", "w:start", "w:hanging", "w:right", "w:end",
            "w:firstLine", "w:firstLineChars",
        ):
            if ind.get(qn(attr)) is not None:
                del ind.attrib[qn(attr)]
    paragraph.paragraph_format.left_indent = Cm(0)
    paragraph.paragraph_format.first_line_indent = Cm(indent_cm)
    pPr = paragraph._p.get_or_add_pPr()
    ind = pPr.find(qn("w:ind"))
    if ind is None:
        ind = OxmlElement("w:ind")
        pPr.append(ind)
    ind.set(qn("w:firstLine"), str(Cm(indent_cm).twips))


def _extract_caption_from_table_first_cell(tbl_elem):
    """Если первый непустой w:p в первой ячейке первой строки таблицы
    начинается с «Таблица», вырезает его из ячейки и возвращает элемент
    (вызывающий код вставит его перед таблицей). Иначе — None.

    Это спасает кейс, когда студент вставил подпись прямо внутрь таблицы
    первой строкой (вместо отдельного абзаца сверху). Sibling-обход такую
    подпись не находит — она «спрятана» внутри `<w:tc>`.

    Если после извлечения ячейка осталась без единого `<w:p>`, вставляем
    пустой — иначе Word посчитает документ повреждённым (требование OOXML).
    """
    first_row = tbl_elem.find(qn("w:tr"))
    if first_row is None:
        return None
    first_cell = first_row.find(qn("w:tc"))
    if first_cell is None:
        return None
    for p in first_cell.findall(qn("w:p")):
        text = "".join(t.text or "" for t in p.iter(qn("w:t"))).strip()
        if not text:
            continue
        if not _TABLE_CAPTION_START_RE.match(text):
            return None
        first_cell.remove(p)
        if first_cell.find(qn("w:p")) is None:
            from docx.oxml import OxmlElement
            first_cell.append(OxmlElement("w:p"))
        return p
    return None


def _table_has_preceding_caption(tbl_elem) -> bool:
    """True, если непосредственно перед таблицей стоит абзац-подпись
    «Таблица ...» (пустые абзацы между подписью и таблицей разрешены)."""
    prev = tbl_elem.getprevious()
    while prev is not None:
        tag = prev.tag.split("}")[-1] if "}" in prev.tag else prev.tag
        if tag == "tbl":
            # Сразу перед таблицей идёт другая таблица — никаких подписей
            # между ними не было.
            return False
        if tag != "p":
            return False
        text = "".join(t.text or "" for t in prev.iter(qn("w:t"))).strip()
        if not text:
            prev = prev.getprevious()
            continue
        return bool(_TABLE_CAPTION_START_RE.match(text))
    return False


def move_table_captions_before_tables(doc) -> int:
    """Перемещает подписи таблиц, расположенные ПОСЛЕ таблицы, на позицию
    ПЕРЕД ней. Возвращает число перемещённых подписей.

    Алгоритм: одиночный проход по телу документа. Для каждой w:tbl без
    подписи СВЕРХУ ищем первый непустой абзац среди непосредственных
    следующих сиблингов; если он начинается с «Таблица», переставляем
    его перед таблицей с помощью lxml.addprevious.

    Защита от воровства подписи у соседней таблицы: если у текущей
    таблицы уже есть подпись сверху, ничего не двигаем — иначе мы бы
    подобрали подпись СЛЕДУЮЩЕЙ таблицы (когда таблицы стоят плотно).
    """
    body = doc.element.body
    moved = 0
    while True:
        changed = False
        children = list(body)
        for i, elem in enumerate(children):
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag != "tbl":
                continue
            if _table_has_preceding_caption(elem):
                # У таблицы уже есть подпись наверху — не трогаем, иначе
                # утащим к ней подпись следующей таблицы.
                continue
            sibling_found = False
            for j in range(i + 1, len(children)):
                next_elem = children[j]
                next_tag = next_elem.tag.split("}")[-1] if "}" in next_elem.tag else next_elem.tag
                if next_tag == "tbl":
                    break
                if next_tag != "p":
                    continue
                text = "".join(
                    t.text or "" for t in next_elem.iter(qn("w:t"))
                ).strip()
                if not text:
                    continue
                if _TABLE_CAPTION_START_RE.match(text):
                    elem.addprevious(next_elem)
                    moved += 1
                    changed = True
                    sibling_found = True
                break
            if changed:
                break
            # Sibling-обход не нашёл подпись — пробуем достать её из первой
            # ячейки самой таблицы. Это типовой кейс: студент написал
            # «Таблица 1 — Название» первой строкой шапки таблицы вместо
            # отдельного абзаца перед ней.
            if not sibling_found:
                extracted = _extract_caption_from_table_first_cell(elem)
                if extracted is not None:
                    elem.addprevious(extracted)
                    moved += 1
                    changed = True
                    break
        if not changed:
            break
    return moved


FIGURE_START_RE = re.compile(r"^(рисунок|рис\.)\b", re.IGNORECASE)
TABLE_START_RE = re.compile(r"^(таблица|табл\.)\b", re.IGNORECASE)
# Авто-надпись над страницей-продолжением разрезанной таблицы
# («Продолжение таблицы N», table_continuation._LABEL_PREFIX). Это НЕ
# ссылка на таблицу из текста — иначе разрезанная таблица ложно считается
# «упомянутой» и table_not_referenced для неё не выдаётся.
TABLE_CONTINUATION_RE = re.compile(
    r"^\s*(продолжение|окончание)\s+таблиц", re.IGNORECASE
)

# Строгий предфильтр для мутирующих операций: за «Таблица»/«табл.» должна
# идти цифра или тире-разделитель, а не произвольный текст предложения.
_TABLE_CAPTION_START_RE = re.compile(
    r"^(таблица|табл\.)\s+\d+(?:\.\d+)*(?:\s*[:–—-]\s*|\.\s+)\S",
    re.IGNORECASE,
)

def _set_keep_flags(p_elem, keep_next: bool, keep_lines: bool) -> None:
    """Проставляет/снимает <w:keepNext/> и <w:keepLines/> в w:pPr.

    Принимает lxml-элемент <w:p> (CT_P). keepNext держит абзац на одной
    странице со следующим (картинка ↔ подпись, подпись таблицы ↔ таблица);
    keepLines не даёт разорвать сам абзац (многострочную подпись) между
    страницами. Порядок дочерних элементов w:pPr по схеме:
    w:pStyle, w:keepNext, w:keepLines, ...
    """
    pPr = p_elem.get_or_add_pPr()
    for tag in ("w:keepNext", "w:keepLines"):
        for existing in list(pPr.findall(qn(tag))):
            pPr.remove(existing)
    pStyle = pPr.find(qn("w:pStyle"))
    anchor = pStyle  # вставляем сразу после w:pStyle (или в начало)
    for want, tag in ((keep_lines, "w:keepLines"), (keep_next, "w:keepNext")):
        if not want:
            continue
        el = OxmlElement(tag)
        el.set(qn("w:val"), "true")
        if anchor is None:
            pPr.insert(0, el)
        else:
            anchor.addnext(el)


def _has_image(paragraph) -> bool:
    el = paragraph._element
    return bool(
        el.findall(".//" + qn("w:drawing"))
        or el.findall(".//" + qn("w:pict"))
        or el.findall(".//" + qn("w:object"))
    )


def _prev_visible_has_image(paragraphs, idx: int) -> bool:
    """True, если ближайший непустой абзац перед `idx` содержит картинку
    (типичная раскладка: рисунок, затем подпись под ним)."""
    j = idx - 1
    while j >= 0:
        p = paragraphs[j]
        if _has_image(p):
            return True
        if (p.text or "").strip():
            return False
        j -= 1
    return False


def _next_visible_sibling_is_table(paragraph) -> bool:
    """True, если следующий непустой XML-сиблинг абзаца — w:tbl.

    Между подписью таблицы и самой таблицей допускаются пустые абзацы.
    """
    sibling = paragraph._element.getnext()
    while sibling is not None:
        tag = sibling.tag
        if tag == qn("w:tbl"):
            return True
        if tag == qn("w:p"):
            text = "".join(t.text or "" for t in sibling.iter(qn("w:t"))).strip()
            if text:
                return False  # непустой абзац перед таблицей — это не подпись
        sibling = sibling.getnext()
    return False


@dataclass
class Caption:
    paragraph_index: int
    original_number: str | None
    new_number: int | str
    title: str
    kind: str  # "figure" или "table"


_APPENDIX_LETTER_RE = re.compile(r"^приложение\s+([а-яё])\b", re.IGNORECASE)


def _chapter_at(para_idx: int, chapter_breaks: list[tuple[int, int]]) -> int:
    """Номер главы, которой принадлежит абзац para_idx (0 = до первой главы)."""
    ch = 0
    for break_idx, num in chapter_breaks:
        if break_idx <= para_idx:
            ch = num
        else:
            break
    return ch


def _collect_captions(
    paragraphs,
    skip_indexes: set[int],
    caption_word: str,
    alignment: WD_ALIGN_PARAGRAPH,
    kind: str,
    renumber: bool,
    indent_cm: float | None = None,
    number_optional: bool = False,
    appendix_aware: bool = False,
    chapter_breaks: list[tuple[int, int]] | None = None,
    require_adjacent_table: bool = False,
) -> tuple[list[Caption], list[tuple[int, str, str]]]:
    # Тире необязательно — автор может написать "Таблица 1 – Foo",
    # "Таблица 1.1. Foo" или просто "Таблица 1.1 Foo". Все три варианта
    # должны давать (number="1[.1]", title="Foo").
    #
    # number_optional=True (листинги): номер может вообще отсутствовать
    # («Листинг — Конфигурация …» — автор забыл номер, мы его проставим
    # сквозной нумерацией). Для рисунков/таблиц номер обязателен, иначе
    # «Рисунок 2 показывает …» (проза) ошибочно станет подписью.
    if number_optional:
        pattern = re.compile(
            rf"^{caption_word}\s*(\d+(?:\.\d+)*)?\s*[:.–—\-]?\s*(.*)$",
            re.IGNORECASE,
        )
        start_pattern = re.compile(rf"^{caption_word}\b", re.IGNORECASE)
        sep_pattern = re.compile(
            rf"^{caption_word}\s*(?:\d+(?:\.\d+)*)?(?:\s*[:–—-]\s*|\.\s+)\S",
            re.IGNORECASE,
        )
    else:
        pattern = re.compile(
            rf"^{caption_word}\s+(\d+(?:\.\d+)*)\s*[:.–—\-]?\s*(.*)$",
            re.IGNORECASE,
        )
        start_pattern = re.compile(rf"^{caption_word}\s+[\d–—\-]", re.IGNORECASE)
        # Настоящая подпись имеет явный разделитель «номер – заголовок».
        # Без него «Рисунок 2 показывает …» — это проза, а не подпись.
        # ВАЖНО: \s+ и точка в символьном классе [:–—-] намеренно исключены:
        # \s+ — любой пробел после цифры превращал прозу в ложную подпись;
        # точка в [:.–—-] — regex мог «найти» разделитель в дробном числе
        # «1.1» через backtracking ((?:\.\d+)* пропускает «.1», «.» матчит класс).
        # Точка как разделитель («Таблица 1. Название») покрыта веткой \.\s+.
        sep_pattern = re.compile(
            rf"^{caption_word}\s+\d+(?:\.\d+)*(?:\s*[:–—-]\s*|\.\s+)\S",
            re.IGNORECASE,
        )

    captions: list[Caption] = []
    changes: list[tuple[int, str, str]] = []  # (paragraph_index, original_text, new_text)

    counter = 1
    current_chapter = 0
    current_appendix: str | None = None
    appendix_counter = 0

    for idx, paragraph in enumerate(paragraphs):
        if idx in skip_indexes:
            continue

        # Нумерация по главам: при смене главы счётчик сбрасывается.
        if chapter_breaks:
            ch = _chapter_at(idx, chapter_breaks)
            if ch != current_chapter:
                current_chapter = ch
                counter = 1

        text = paragraph.text.strip()
        if not text:
            continue

        if appendix_aware:
            m = _APPENDIX_LETTER_RE.match(text)
            if m:
                current_appendix = m.group(1).upper()
                appendix_counter = 0
                continue

        if not start_pattern.match(text):
            continue

        # Для таблиц: подпись обязана стоять непосредственно перед w:tbl
        # (возможно, отделённая пустыми абзацами). Если следующий непустой
        # XML-сиблинг не является таблицей — это проза, а не подпись.
        if require_adjacent_table and not _next_visible_sibling_is_table(paragraph):
            continue

        # Анти-фантом: абзац начинается с «Рисунок N»/«Таблица N», но это
        # проза («Таблица 1.1 показывает …»), а не подпись/надпись.
        # Для таблиц центрирование не является признаком, но признаком прозы
        # является завершающий знак препинания (.!?) — подписи без тире
        # («Таблица 3.2 Показатели качества») его не имеют.
        # Для рисунков оставляем визуальные признаки (центр/картинка).
        if not sep_pattern.match(text):
            if require_adjacent_table:
                # Заканчивается на точку/восклиц./вопрос. — явная проза, не подпись.
                if text and text[-1] in ".!?":
                    continue
            else:
                centered = paragraph.alignment == WD_ALIGN_PARAGRAPH.CENTER
                if not (centered or _prev_visible_has_image(paragraphs, idx)):
                    continue

        match = pattern.match(text)
        if match:
            original_number, title = match.group(1), match.group(2).strip(" –—-:.,")
        else:
            original_number, title = None, text.split(" ", 1)[-1].strip(" –—-,")

        if appendix_aware and current_appendix:
            appendix_counter += 1
            num_val: int | str = f"{current_appendix}.{appendix_counter}"
        elif chapter_breaks and current_chapter > 0:
            num_val = f"{current_chapter}.{counter}"
        else:
            num_val = counter

        cap = Caption(
            paragraph_index=idx,
            original_number=original_number,
            new_number=num_val,
            title=title,
            kind=kind,
        )
        captions.append(cap)

        if renumber:
            # По ГОСТ строка «Таблица N — ...» всегда без абзацного отступа:
            # админ-поле сохраняем для обратной совместимости, но в обработке
            # таблиц применяем только 0.
            effective_indent_cm = 0.0 if kind == "table" else indent_cm
            new_text = f"{caption_word} {num_val} — {title}"
            changed = text != new_text or paragraph.alignment != alignment
            if effective_indent_cm is not None:
                fmt = paragraph.paragraph_format
                current_indent = fmt.first_line_indent
                changed = changed or (current_indent != Cm(effective_indent_cm))
            if changed:
                original_text = text
                overwrite_paragraph_text(paragraph, new_text)
                _set_caption_font(paragraph)
                paragraph.alignment = alignment
                # Нарушение «Нумерация подписи изменена» фиксируем ТОЛЬКО
                # когда реально изменился НОМЕР.
                if (original_number or "") != str(num_val):
                    changes.append((idx, original_text, new_text))
            if effective_indent_cm is not None:
                _apply_caption_indent(paragraph, effective_indent_cm)

        if not (appendix_aware and current_appendix):
            counter += 1

    return captions, changes


def renumber_figures(
    paragraphs,
    skip_indexes: set[int],
    apply: bool,
    chapter_breaks: list[tuple[int, int]] | None = None,
) -> tuple[list[Caption], list[tuple[int, str, str]]]:
    return _collect_captions(
        paragraphs, skip_indexes, "Рисунок", WD_ALIGN_PARAGRAPH.CENTER, "figure", apply,
        chapter_breaks=chapter_breaks,
    )


def renumber_tables(
    paragraphs,
    skip_indexes: set[int],
    apply: bool,
    indent_cm: float | None = None,
    chapter_breaks: list[tuple[int, int]] | None = None,
) -> tuple[list[Caption], list[tuple[int, str, str]]]:
    return _collect_captions(
        paragraphs, skip_indexes, "Таблица", WD_ALIGN_PARAGRAPH.JUSTIFY, "table", apply,
        indent_cm=indent_cm,
        chapter_breaks=chapter_breaks,
        require_adjacent_table=True,
    )


def keep_figures_with_captions(doc, figures: list[Caption], skip_indexes: set[int]) -> None:
    """Рисунок и его подпись не должны разрываться по страницам.

    Подпись рисунка идёт ПОД картинкой. Ставим keepLines на абзац подписи,
    keepNext+keepLines на абзац(ы) с картинкой и keepNext на пустые абзацы
    между ними — так Word держит картинку и подпись на одной странице.
    Best-effort: картинка крупнее страницы всё равно не уместится с подписью,
    keepNext лишь минимизирует разрыв.
    """
    paragraphs = doc.paragraphs
    for cap in figures:
        if cap.kind != "figure":
            continue
        idx = cap.paragraph_index
        if idx in skip_indexes or idx >= len(paragraphs):
            continue
        _set_keep_flags(paragraphs[idx]._p, keep_next=False, keep_lines=True)
        j = idx - 1
        seen_image = False
        while j >= 0:
            p = paragraphs[j]
            if _has_image(p):
                _set_keep_flags(p._p, keep_next=True, keep_lines=True)
                seen_image = True
                j -= 1
                continue
            if (p.text or "").strip():
                break  # дошли до текста/заголовка — стоп
            # пустой абзац-разделитель между картинкой и подписью
            _set_keep_flags(p._p, keep_next=True, keep_lines=False)
            if seen_image:
                break
            j -= 1


def validate_references(
    stats: DocStats,
    figures: list[Caption],
    tables: list[Caption],
    skip_indexes: set[int],
) -> list[PipelineViolation]:
    figure_numbers = {str(cap.new_number) for cap in figures}
    table_numbers = {str(cap.new_number) for cap in tables}

    # Сопоставляем исходные номера автора ("1.1", "2.3", "5") с новыми
    # номерами, выданными перенумерацией. Это позволяет распознать ссылки,
    # которые всё ещё используют старую нумерацию.
    figure_original_map = {
        cap.original_number: str(cap.new_number) for cap in figures if cap.original_number
    }
    table_original_map = {
        cap.original_number: str(cap.new_number) for cap in tables if cap.original_number
    }

    def _resolve_ref(raw: str, original_map: dict[str, str], all_numbers: set[str]) -> str | None:
        if raw in original_map:
            return original_map[raw]
        if raw in all_numbers:
            return raw
        # Целое число возвращаем безусловно — нужно для выявления ссылок
        # на несуществующие подписи (missing_figures / missing_tables).
        try:
            return str(int(raw))
        except ValueError:
            # «1.1» в документе с плоской нумерацией — нечёткое совпадение
            # по головной части: «1.1» → 1.
            head = raw.split(".")[0]
            try:
                s = str(int(head))
                return s if s in all_numbers else None
            except ValueError:
                return None

    figure_refs: set[str] = set()
    table_refs: set[str] = set()
    # Первое место упоминания каждого номера — для якоря в PDF: реальная
    # подстрока («рисунок 9») + индекс абзаца. Иначе непонятно, где искать.
    fig_ref_loc: dict[str, tuple[int, str]] = {}
    tbl_ref_loc: dict[str, tuple[int, str]] = {}

    # Пропускаем только сами абзацы-подписи, а не все «Таблица…» / «Рисунок…»
    # в тексте: «Таблица 1.1 показывает, что…» — валидная ссылка, не подпись.
    caption_idxs: set[int] = {cap.paragraph_index for cap in figures} | {
        cap.paragraph_index for cap in tables
    }

    from services.core.vkr_core.engine.crossref import iter_reference_spans

    for ps in stats.paragraphs:
        if ps.index in skip_indexes or ps.is_empty:
            continue
        lowered = ps.stripped.lower()
        if ps.index in caption_idxs:
            continue
        if TABLE_CONTINUATION_RE.match(lowered):
            continue  # «Продолжение таблицы N» — авто-надпись, не ссылка

        # iter_reference_spans разворачивает перечисления («рисунки 2.3 и
        # 2.4», «табл. 5, 6») — каждый номер учитывается отдельно, иначе
        # вторая ссылка терялась и рисунок числился «не упомянутым».
        for kind, num, phrase in iter_reference_spans(ps.stripped):
            if kind == "figure":
                resolved = _resolve_ref(num, figure_original_map, figure_numbers)
                if resolved is not None:
                    figure_refs.add(resolved)
                    fig_ref_loc.setdefault(resolved, (ps.index, phrase))
            else:
                resolved = _resolve_ref(num, table_original_map, table_numbers)
                if resolved is not None:
                    table_refs.add(resolved)
                    tbl_ref_loc.setdefault(resolved, (ps.index, phrase))

    violations: list[PipelineViolation] = []
    for cap in figures:
        if str(cap.new_number) not in figure_refs:
            violations.append(
                PipelineViolation(
                    type="figure_not_referenced",
                    rule_reference="п. 6.12",
                    description=(
                        f"Рисунок {cap.new_number} пока не упомянут в тексте. "
                        f"Совет: добавьте короткую ссылку рядом с обсуждением иллюстрации, "
                        f"например «см. рисунок {cap.new_number}»."
                    ),
                    status=ViolationStatus.manual_required,
                    severity=SEVERITY_INFO,
                    paragraph_index=cap.paragraph_index,
                    original_text=f"Рисунок {cap.new_number} — {cap.title}",
                )
            )
    for cap in tables:
        if str(cap.new_number) not in table_refs:
            violations.append(
                PipelineViolation(
                    type="table_not_referenced",
                    rule_reference="п. 6.13",
                    description=(
                        f"Таблица {cap.new_number} пока не упомянута в тексте. "
                        f"Совет: добавьте короткую ссылку рядом с обсуждением данных, "
                        f"например «см. таблицу {cap.new_number}»."
                    ),
                    status=ViolationStatus.manual_required,
                    severity=SEVERITY_INFO,
                    paragraph_index=cap.paragraph_index,
                    original_text=f"Таблица {cap.new_number} — {cap.title}",
                )
            )

    missing_figures = figure_refs - figure_numbers
    for number in sorted(missing_figures):
        loc = fig_ref_loc.get(number)
        violations.append(
            PipelineViolation(
                type="figure_reference_missing",
                rule_reference="п. 6.12",
                description=f"В тексте ссылка на рисунок {number}, а сам рисунок отсутствует.",
                status=ViolationStatus.manual_required,
                severity=SEVERITY_WARNING,
                paragraph_index=loc[0] if loc else None,
                original_text=loc[1] if loc else None,
            )
        )

    missing_tables = table_refs - table_numbers
    for number in sorted(missing_tables):
        loc = tbl_ref_loc.get(number)
        violations.append(
            PipelineViolation(
                type="table_reference_missing",
                rule_reference="п. 6.13",
                description=(
                    f"В тексте есть ссылка на таблицу {number}, но такой таблицы не найдено. "
                    "Совет: проверьте номер ссылки или добавьте соответствующую таблицу."
                ),
                status=ViolationStatus.manual_required,
                severity=SEVERITY_INFO,
                paragraph_index=loc[0] if loc else None,
                original_text=loc[1] if loc else None,
            )
        )

    return violations
