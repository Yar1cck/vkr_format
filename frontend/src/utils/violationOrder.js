// Единый порядок ленты замечаний (используют StudentPage и StaffPage).
//
// В первую очередь — то, что ТРЕБУЕТ ВЫБОРА пользователя (подтвердить
// заголовок, выбрать номер и т.п.): такие карточки нельзя пропустить, они
// должны быть наверху. Затем — прочие ручные, авто-исправленные и решённые.

const SEVERITY_ORDER = { critical: 0, warning: 1, info: 2 };

// Типы, которые по своей сути требуют решения пользователя (в карточке есть
// кнопки выбора: Применить / Принять / Отменить исправление / Это не заголовок).
const CHOICE_TYPES = new Set([
  'heading_confirm',
  'heading_number_conflict',
  'possible_missed_heading',
  // Перенумерация подписей — карточка предлагает «Принять / Отменить».
  'caption_renumbered',
  'figures_renumbered',
  'tables_renumbered',
]);

function needsChoice(v) {
  if (v.status !== 'manual_required') return false;
  return (Array.isArray(v.fix_options) && v.fix_options.length > 0)
    || CHOICE_TYPES.has(v.type);
}

// 0 — требует выбора, 1 — прочие manual_required, 2 — auto_fixed,
// 3 — accepted/rejected/прочее.
function statusGroup(v) {
  if (needsChoice(v)) return 0;
  if (v.status === 'manual_required') return 1;
  if (v.status === 'auto_fixed') return 2;
  return 3;
}

export function compareViolations(a, b) {
  const ga = statusGroup(a);
  const gb = statusGroup(b);
  if (ga !== gb) return ga - gb;
  const sa = SEVERITY_ORDER[a.severity] ?? 3;
  const sb = SEVERITY_ORDER[b.severity] ?? 3;
  if (sa !== sb) return sa - sb;
  const pa = a.paragraph_index ?? Number.MAX_SAFE_INTEGER;
  const pb = b.paragraph_index ?? Number.MAX_SAFE_INTEGER;
  return pa - pb;
}

export function sortViolations(list) {
  return [...(list ?? [])].sort(compareViolations);
}
