// Русские подписи и Tailwind-бейджи статусов, ролей и approval'ов.
// Раньше эти словари жили копиями в StaffPage, AdminPage, StudentPage,
// DashboardView, Layout — теперь единая точка правды.
//
// SEVERITY_RU (русские названия серьёзностей) — в utils/violationLabels.js,
// сюда не дублируется.

// --- Статус обработки документа ----------------------------------------------

export const STATUS_LABELS = {
  pending:    'Ожидает',
  processing: 'Обрабатывается',
  done:       'Готово',
  error:      'Ошибка',
};

// Цвет точки-индикатора для статуса (Staff, Dashboard).
export const STATUS_DOT = {
  pending:    'bg-slate-300',
  processing: 'bg-amber-400',
  done:       'bg-emerald-500',
  error:      'bg-red-500',
};

// --- Approval (одобрение работы руководителем/деканом) -----------------------

export const APPROVAL_LABELS = {
  pending_review: 'На проверке',
  approved:       'Принят',
  rejected:       'Отклонён',
};

export const APPROVAL_BADGE = {
  pending_review: 'bg-amber-100 text-amber-800',
  approved:       'bg-emerald-100 text-emerald-800',
  rejected:       'bg-red-100 text-red-800',
};

// --- Роли пользователя -------------------------------------------------------

export const ROLE_LABELS = {
  student:    'Студент',
  supervisor: 'Руководитель',
  dean:       'Декан',
  admin:      'Администратор',
};

// Вариант для AdminPage — там используется полное «Научный руководитель».
export const ROLE_LABELS_ADMIN = {
  ...ROLE_LABELS,
  supervisor: 'Научный руководитель',
};

// Вариант для StudentPage — студент видит себя как «Вы».
export const ROLE_LABELS_STUDENT = {
  ...ROLE_LABELS,
  student: 'Вы',
};

// --- Серьёзность нарушения (CSS-бейджи; русские названия — в violationLabels) -

export const SEVERITY_BADGE = {
  critical: 'bg-red-100 text-red-700',
  warning:  'bg-amber-100 text-amber-700',
  info:     'bg-emerald-100 text-emerald-700',
  error:    'bg-red-100 text-red-800',
};
