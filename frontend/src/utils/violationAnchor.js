// Текст-«якорь» нарушения — строка, которую PdfPane ищет в текстовом слое
// PDF, чтобы подсветить нарушение и пролистать к нему.
//
// Движок заполняет два потенциально-якорных поля:
//   • section_title — полный текст заголовка/подписи ("1. Введение",
//     "Таблица 2 – ..."), задаётся для заголовков и подписей таблиц;
//   • original_text — точный оффендинг-фрагмент: запрещённый заголовок,
//     формула, строка библиографии, перенумерованная подпись рисунка,
//     номер ссылки ("[3-5]") и т.п.
//
// Берём самый длинный из непустых: длинная строка уникальнее и надёжнее
// матчится в PDF, чем короткий числовой префикс ("1", "[1]"). PdfPane сам
// отбрасывает needle короче 3 символов и умеет искать по укороченному
// префиксу, поэтому здесь достаточно вернуть «лучшее, что есть», а где
// якоря нет вовсе (объём, отсутствующий раздел, общедокументное
// форматирование) — вернуть null, и нарушение просто не будет кликабельным.
//
// Исключение — нарушения, где правка УЖЕ применена к документу: подпись
// перенумерована ("Рисунок 2.1 — …" → "Рисунок 1 — …"), запрещённый
// заголовок переименован и т.п. В исправленном PDF старого текста
// (original_text) больше нет, есть только новый (fixed_text) — для них
// якорь должен указывать на fixed_text, иначе переход не сработает.
// Замечания, чей якорь короткий и встречается в тексте многократно (ссылки
// «[N]»). Постоянное жёлтое подчёркивание всех «[9]» было бы шумом, поэтому
// эти типы подсвечиваются ТОЛЬКО когда выбрана их карточка (через activeText),
// а в общий список highlights не попадают.
export const ACTIVE_ONLY_ANCHOR_TYPES = new Set([
  'citation_without_source',
  'citation_sequence_issue',
  'citation_separator_missing',
  'citation_range_suspicious',
  'figure_reference_missing',
  'table_reference_missing',
]);

const FIXED_TEXT_ANCHOR_TYPES = new Set([
  'caption_renumbered',
  'figures_renumbered',
  'tables_renumbered',
  'forbidden_heading',
  'heading_rename',
]);

export function violationNeedle(v) {
  if (!v) return null;
  const preferFixed =
    (FIXED_TEXT_ANCHOR_TYPES.has(v.type) || v.status === 'auto_fixed') &&
    typeof v.fixed_text === 'string' &&
    v.fixed_text.trim();
  if (preferFixed) return v.fixed_text.trim();
  let best = null;
  for (const c of [v.section_title, v.original_text]) {
    if (typeof c !== 'string') continue;
    const t = c.trim();
    if (!t) continue;
    if (!best || t.length > best.length) best = t;
  }
  return best;
}
