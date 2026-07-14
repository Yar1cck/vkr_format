// Единый словарь русских названий для замечаний, причин (detector_signals),
// важности и статуса. В пользовательской части сервиса НЕ должно быть сырых
// английских идентификаторов (раздел админа — исключение).
//
// ВНИМАНИЕ: VIOLATION_TYPE_RU дублируется в бэкенде
// (services/core/vkr_core/engine/violation_labels.py) для PDF-отчёта —
// codebase разные, единый источник невозможен. При добавлении нового типа
// нарушения пополнять ОБА файла.

export const SEVERITY_RU = {
  critical: 'Критично',
  warning:  'Предупреждение',
  info:     'Информация',
};

export const VIOLATION_STATUS_RU = {
  auto_fixed:      'Исправлено автоматически',
  manual_required: 'Требует проверки',
  accepted:        'Принято',
  rejected:        'Отклонено',
};

// Человекочитаемые причины — без жаргона. Признаки оформления (полужирный,
// центрирование, размер шрифта) указаны «в исходном файле», потому что в
// исправленном документе тело приводится к ГОСТ и они снимаются — иначе на
// превью «жирного» не видно, а подпись про него сбивает с толку.
// Сигнал кодируется как "name" или "name:value"; value — только для инфо.
export const SIGNAL_RU = {
  native_style:        'В Word помечен стилем заголовка',
  native_style_empty:  'Пустая строка со стилем заголовка',
  outline_level:       'В Word отмечен как уровень структуры (заголовок)',
  numpr_ilvl:          'Входит в автоматический список Word',
  chapter_word:        'Начинается со слова «Глава» или «Раздел»',
  appendix:            'Начинается со слова «Приложение»',
  structural_keyword:  'Совпадает с названием раздела (Введение, Заключение и т.п.)',
  literal_number:      'Начинается с номера вида 1.2.3',
  font_large:          'Шрифт крупнее обычного текста (в исходном файле)',
  font_small:          'Шрифт чуть крупнее обычного (в исходном файле)',
  bold:                'Полужирный в исходном файле (в исправленном снят по ГОСТ)',
  bold_partial:        'Частично полужирный в исходном файле',
  centered:            'Выровнен по центру в исходном файле',
  all_caps:            'Набран ЗАГЛАВНЫМИ буквами',
  short:               'Короткая строка',
  isolated:            'Стоит отдельно между длинными абзацами',
  no_period:           'Без точки в конце',
  page_break_before:   'Начинается с новой страницы',
  after_heading:       'Идёт сразу после другого заголовка',
  hanging_indent_penalty: 'Скорее против: оформлен с отступом как пункт списка',
  lowercase_start:     'Скорее против: начинается со строчной буквы',
  internal_sentence:   'Скорее против: внутри строки есть конец предложения',
  ends_with_colon:     'Скорее против: оканчивается двоеточием',
  dense_text:          'Скорее против: длинный текст с запятыми, как обычный абзац',
  no_strong_signal_capped: 'Нет ни одного сильного признака заголовка — уверенность понижена',
};

export function humaniseSignal(sig) {
  const [name, value] = String(sig).split(':', 2);
  const label = SIGNAL_RU[name] ?? 'Иной признак оформления';
  return value ? `${label} (${value})` : label;
}

export const VIOLATION_TYPE_RU = {
  // Структура
  missing_structural_section:        'Отсутствует обязательный раздел',
  structural_order_violation:        'Нарушен порядок разделов',
  // Приложения
  appendix_letter_invalid:           'Недопустимая буква приложения',
  appendix_letter_gap:               'Пропуск в нумерации приложений',
  appendix_not_referenced:           'Приложение не упомянуто в тексте',
  appendix_order_violation:          'Порядок приложений нарушен',
  // Ссылки и источники
  citation_sequence_issue:           'Нарушен порядок ссылок',
  citation_without_source:           'Ссылка без источника в списке',
  citation_separator_missing:        'Нет разделителя между ссылками',
  citation_combined:                 'Несколько источников в одной скобке — разбито',
  citation_range_suspicious:         'Подозрительный диапазон ссылок',
  source_not_cited:                  'Источник не упомянут в тексте',
  bibliography_missing:              'Список источников отсутствует',
  bibliography_numbering_gap:        'Нарушена нумерация источников',
  bibliography_entry_incomplete:     'Неполная запись источника',
  bibliography_entry_malformed:      'Некорректный номер записи источника',
  bibliography_entries_unrecognised: 'Записи источников не распознаны',
  // Заголовки
  forbidden_heading:                 'Недопустимый заголовок',
  heading_rename:                    'Заголовок раздела приведён к канону',
  heading_number_conflict:           'Конфликт нумерации заголовка',
  heading_confirm:                   'Возможный заголовок — подтвердите',
  possible_missed_heading:           'Возможный пропущенный заголовок',
  heading_recovered:                 'Восстановлен пропущенный заголовок',
  // Рисунки/таблицы/формулы
  figures_renumbered:                'Нумерация рисунков исправлена',
  tables_renumbered:                 'Нумерация таблиц исправлена',
  caption_renumbered:                'Нумерация подписи изменена',
  figure_not_referenced:             'Рисунок без ссылки в тексте',
  figure_reference_missing:          'Ссылка на несуществующий рисунок',
  table_not_referenced:              'Таблица без ссылки в тексте',
  table_reference_missing:           'Ссылка на несуществующую таблицу',
  formula_without_explanation:       'Формула без пояснения символов',
  formula_numbering_gap:             'Нарушена нумерация формул',
  // Объём и оформление
  volume_below_minimum:              'Объём ниже допустимого',
  volume_above_maximum:              'Объём превышает допустимый',
  font_size_inconsistency:           'Разные размеры шрифта в тексте',
  table_mass_bold_removed:           'Снято сплошное выделение в таблице',
  long_table_split_warning:          'Длинная таблица разрезана для переноса',
  paragraph_spacing:                 'Межстрочный интервал/отступы абзаца',
};

// Никогда не возвращаем сырой английский id — неизвестный тип получает
// нейтральную русскую подпись.
export function violationTypeLabel(type) {
  return VIOLATION_TYPE_RU[type] ?? 'Замечание оформления';
}
