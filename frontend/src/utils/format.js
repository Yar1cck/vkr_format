// Форматирование дат и размеров — раньше разными копиями жило в
// StudentPage, StaffPage, AdminPage, DashboardView. Единая точка
// правды и единое поведение во всех ролях.

const _ru = (iso) => {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d;
};

// «25.04.2026 14:30» — стандартный формат для всех мест, где нужны дата и время.
export const fmtDate = (iso) => {
  const d = _ru(iso);
  if (!d) return '—';
  const date = d.toLocaleDateString('ru-RU', {
    day: '2-digit', month: '2-digit', year: 'numeric',
  });
  const time = d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  return `${date} ${time}`;
};

// Короткий формат «25.04.26, 14:30» (для таблиц/чатов, где места меньше).
export const fmtDateShort = (iso) => {
  const d = _ru(iso);
  if (!d) return '';
  return d.toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' });
};

// Компактный формат «25.04» — только день и месяц.
// Для маленьких ячеек в дашборде, где год не нужен.
export const fmtDateCompact = (iso) => {
  const d = _ru(iso);
  if (!d) return '';
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
};

// Размер файла → человекочитаемое значение в КБ/МБ.
export const fmtSize = (bytes) => {
  if (!bytes) return '—';
  if (bytes >= 1048576) return `${(bytes / 1048576).toFixed(1)} МБ`;
  return `${Math.round(bytes / 1024)} КБ`;
};
