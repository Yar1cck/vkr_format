"""Перекрёстные ссылки на рисунки и таблицы (ТЗ §7.3).

Подписи перенумеровываются в `captions.py` (например, «Рисунок 2.1 – …»
→ «Рисунок 1 – …»). Но ссылки в тексте при этом оставались со старыми
номерами — документ становился внутренне несогласованным. Этот модуль:

1. перенумеровывает ссылки в тексте по карте {старый № → новый №},
   понимая перечисления вида «рисунки 2.3 и 2.4», «табл. 5, 6»;
2. ставит закладку на каждую подпись;
3. оборачивает каждую ссылку во внутреннюю гиперссылку на эту закладку
   (кликабельно в Word и LibreOffice, переживает пересохранение LO —
   без хрупких REF-полей).

Никакого LLM/эвристик — чистая детерминированная замена по регулярке.
"""

from __future__ import annotations

import re

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

# Слово-ссылка + число(а). Поддерживаются падежные формы и перечисления:
#   "рисунок 2.1", "на рисунке 3", "рисунки 2.3 и 2.4", "табл. 5, 6 и 7".
_REF_RE = re.compile(
    r"(?P<word>рисунок|рисунк\w*|рис\.?|таблица|таблиц\w*|табл\.?)"
    r"(?P<sp>[№   ]*)"
    r"(?P<nums>\d+(?:\.\d+)*(?:[   ]*(?:,|и)[   ]*\d+(?:\.\d+)*)*)",
    re.IGNORECASE,
)
_NUM_RE = re.compile(r"\d+(?:\.\d+)*")
# Разбиение перечисления с сохранением разделителей: "2.3 и 2.4" →
# ["2.3", " и ", "2.4"].
_NUMS_SPLIT_RE = re.compile(r"([   ]*(?:,|и)[   ]*)")

FIGURE_BOOKMARK = "_Ref_fig{}"
TABLE_BOOKMARK = "_Ref_tbl{}"


def _bm_name(template: str, num) -> str:
    """Имя закладки: точки в номере заменяются на '_' (Word не допускает '.' в именах)."""
    return template.format(str(num).replace(".", "_"))


def _kind(word: str) -> str:
    return "figure" if word.lower().startswith("рис") else "table"


def iter_reference_spans(text: str):
    """Yield (kind, number_str, raw_phrase) для каждой ссылки в тексте,
    разворачивая перечисления. raw_phrase — сырая подстрока («рисунок 9»,
    «рисунки 2.3 и 2.4»)."""
    for m in _REF_RE.finditer(text):
        kind = _kind(m.group("word"))
        phrase = m.group(0)
        for num in _NUM_RE.findall(m.group("nums")):
            yield kind, num, phrase


def _run(text: str):
    """Обычный run Times New Roman 14pt — внешний вид ссылки не меняем,
    только делаем её кликабельной."""
    r = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")
    rFonts = OxmlElement("w:rFonts")
    rFonts.set(qn("w:ascii"), "Times New Roman")
    rFonts.set(qn("w:hAnsi"), "Times New Roman")
    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), "28")  # 14pt в полупунктах
    rPr.append(rFonts)
    rPr.append(sz)
    r.append(rPr)
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = text
    r.append(t)
    return r


def _hyperlink(text: str, anchor: str):
    h = OxmlElement("w:hyperlink")
    h.set(qn("w:anchor"), anchor)
    h.append(_run(text))
    return h


def _ensure_bookmark(p_elem, name: str, bm_id: int) -> None:
    """bookmarkStart/End сразу после pPr (или в начало абзаца)."""
    # Идемпотентность: не плодим одинаковые закладки при повторном прогоне.
    for bm in p_elem.findall(qn("w:bookmarkStart")):
        if bm.get(qn("w:name")) == name:
            return
    bm_start = OxmlElement("w:bookmarkStart")
    bm_start.set(qn("w:id"), str(bm_id))
    bm_start.set(qn("w:name"), name)
    bm_end = OxmlElement("w:bookmarkEnd")
    bm_end.set(qn("w:id"), str(bm_id))
    pPr = p_elem.find(qn("w:pPr"))
    if pPr is not None:
        pPr.addnext(bm_end)
        pPr.addnext(bm_start)
    else:
        p_elem.insert(0, bm_end)
        p_elem.insert(0, bm_start)


def _resolve(num: str, number_map: dict[str, int | str], valid_new: set[int | str]):
    """Старый номер → новый. Если ссылка уже использует финальную
    нумерацию — оставляем как есть. Иначе None (ссылка «висячая»)."""
    if num in number_map:
        return number_map[num]
    if num in valid_new:
        return num
    try:
        as_int = int(num)
        return as_int if as_int in valid_new else None
    except ValueError:
        return None


def _rebuild_paragraph(paragraph, fig_map, tbl_map, fig_valid, tbl_valid) -> bool:
    """Перестраивает runs абзаца: ссылки → новый номер + гиперссылка.
    Возвращает True, если абзац был изменён."""
    text = paragraph.text or ""
    if not _REF_RE.search(text):
        return False

    # segments: список (текст, anchor|None) — None = обычный текст.
    segments: list[tuple[str, str | None]] = []
    pos = 0
    changed = False
    for m in _REF_RE.finditer(text):
        if m.start() > pos:
            segments.append((text[pos:m.start()], None))
        kind = _kind(m.group("word"))
        number_map = fig_map if kind == "figure" else tbl_map
        valid_new = fig_valid if kind == "figure" else tbl_valid
        bm_tpl = FIGURE_BOOKMARK if kind == "figure" else TABLE_BOOKMARK

        segments.append((m.group("word") + m.group("sp"), None))
        parts = _NUMS_SPLIT_RE.split(m.group("nums"))
        for part in parts:
            if _NUM_RE.fullmatch(part):
                new_num = _resolve(part, number_map, valid_new)
                if new_num is None:
                    segments.append((part, None))  # висячая ссылка — не трогаем
                else:
                    if part != str(new_num):
                        changed = True
                    segments.append((str(new_num), _bm_name(bm_tpl, new_num)))
            else:
                segments.append((part, None))  # разделитель ", " / " и "
        pos = m.end()
    if pos < len(text):
        segments.append((text[pos:], None))

    # Гиперссылку добавляем всегда (даже если номер не менялся) — это и есть
    # «якорь к тексту», которого раньше не было.
    has_link = any(anchor for _, anchor in segments)
    if not changed and not has_link:
        return False

    p = paragraph._p
    for child in list(p):
        tag = child.tag
        if tag == qn("w:r") or tag == qn("w:hyperlink"):
            p.remove(child)

    for seg_text, anchor in segments:
        if not seg_text:
            continue
        if anchor:
            p.append(_hyperlink(seg_text, anchor))
        else:
            p.append(_run(seg_text))
    return True


def apply_crossrefs(doc, figures, tables, skip_indexes: set[int]) -> int:
    """Ставит закладки на подписи и перенумеровывает + оборачивает в
    гиперссылки все ссылки в тексте. Возвращает число изменённых абзацев.

    `figures` / `tables` — списки Caption (см. captions.py): нужны поля
    `original_number`, `new_number`, `paragraph_index`.
    """
    def _build_map(caps):
        m: dict[str, int | str] = {}
        valid: set[int | str] = set()
        for c in caps:
            valid.add(c.new_number)
            if c.original_number:
                m[c.original_number] = c.new_number
            # Ссылка, уже использующая финальный номер, тоже должна
            # становиться кликабельной.
            m.setdefault(str(c.new_number), c.new_number)
        return m, valid

    fig_map, fig_valid = _build_map(figures)
    tbl_map, tbl_valid = _build_map(tables)

    paragraphs = doc.paragraphs
    caption_idx = {c.paragraph_index for c in figures} | {
        c.paragraph_index for c in tables
    }

    # Закладки на подписи.
    bm_id = 90000
    for c in figures:
        if c.paragraph_index < len(paragraphs):
            _ensure_bookmark(
                paragraphs[c.paragraph_index]._p,
                _bm_name(FIGURE_BOOKMARK, c.new_number),
                bm_id,
            )
            bm_id += 1
    for c in tables:
        if c.paragraph_index < len(paragraphs):
            _ensure_bookmark(
                paragraphs[c.paragraph_index]._p,
                _bm_name(TABLE_BOOKMARK, c.new_number),
                bm_id,
            )
            bm_id += 1

    changed = 0
    for idx, paragraph in enumerate(paragraphs):
        if idx in skip_indexes or idx in caption_idx:
            continue
        if _rebuild_paragraph(
            paragraph, fig_map, tbl_map, fig_valid, tbl_valid
        ):
            changed += 1
    return changed
