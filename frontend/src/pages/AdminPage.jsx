import React, { useEffect, useMemo, useState } from 'react';

import api from '../api/client';
import Layout from '../components/Layout';
import DashboardView from '../components/DashboardView';
import { fmtDate as formatDate } from '../utils/format';
import {
  APPROVAL_BADGE,
  APPROVAL_LABELS,
  ROLE_LABELS_ADMIN as ROLE_LABELS,
  STATUS_LABELS,
} from '../utils/labels';


const ADMIN_NAV_ITEMS = [
  { id: 'overview',  label: 'Обзор' },
  { id: 'users',     label: 'Пользователи' },
  { id: 'documents', label: 'Работы' },
  { id: 'config',    label: 'Конфигурация' },
];


// ── Переиспользуемые поля формы ───────────────────────────────────────────────

function NumberField({ label, value, onChange, step = 1, min, hint }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-slate-600">{label}</span>
      <input
        type="number"
        className="input"
        value={value ?? ''}
        step={step}
        min={min}
        onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
      />
      {hint && <span className="text-xs text-slate-400">{hint}</span>}
    </label>
  );
}


function TextField({ label, value, onChange, placeholder, hint }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-slate-600">{label}</span>
      <input
        type="text"
        className="input"
        value={value ?? ''}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
      {hint && <span className="text-xs text-slate-400">{hint}</span>}
    </label>
  );
}


function SelectField({ label, value, options, onChange }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-slate-600">{label}</span>
      <select className="input" value={value ?? ''} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  );
}


function CheckboxField({ label, value, onChange }) {
  return (
    <label className="inline-flex items-center gap-2 text-sm text-slate-600">
      <input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}


function ArrayTextarea({ label, value, onChange, placeholder }) {
  // Редактор массивов строк (по одной строке в строке textarea).
  // Используется для алиасов структурных элементов.
  const text = Array.isArray(value) ? value.join('\n') : '';
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-slate-600">{label}</span>
      <textarea
        className="input min-h-[80px] font-mono text-xs"
        value={text}
        placeholder={placeholder}
        onChange={(e) => {
          const lines = e.target.value.split('\n').map((s) => s.trim()).filter(Boolean);
          onChange(lines);
        }}
      />
    </label>
  );
}


function KeyValueEditor({ label, value, onChange, keyPlaceholder, valuePlaceholder }) {
  // Редактор для словаря вида {ключ: значение|null}, который использует
  // forbidden_heading_map.
  const entries = Object.entries(value ?? {});
  const updateKey = (i, newKey) => {
    const next = entries.map(([k, v], idx) => [idx === i ? newKey : k, v]);
    const obj = Object.fromEntries(next);
    onChange(obj);
  };
  const updateValue = (i, newVal) => {
    const next = entries.map(([k, v], idx) => [k, idx === i ? (newVal === '' ? null : newVal) : v]);
    onChange(Object.fromEntries(next));
  };
  const removeRow = (i) => {
    const next = entries.filter((_, idx) => idx !== i);
    onChange(Object.fromEntries(next));
  };
  const addRow = () => {
    onChange({ ...(value ?? {}), '': null });
  };
  return (
    <div className="flex flex-col gap-2 text-sm">
      <span className="text-slate-600">{label}</span>
      <div className="space-y-2">
        {entries.map(([k, v], i) => (
          <div key={i} className="flex gap-2">
            <input
              className="input flex-1"
              value={k}
              placeholder={keyPlaceholder}
              onChange={(e) => updateKey(i, e.target.value)}
            />
            <input
              className="input flex-1"
              value={v ?? ''}
              placeholder={valuePlaceholder ?? 'замена (пусто — удалить)'}
              onChange={(e) => updateValue(i, e.target.value)}
            />
            <button type="button" className="rounded-lg border border-rose-300 px-2 text-xs text-rose-600 hover:bg-rose-50" onClick={() => removeRow(i)}>
              ✕
            </button>
          </div>
        ))}
      </div>
      <button type="button" className="self-start rounded-lg border border-slate-300 px-3 py-1 text-xs hover:bg-slate-50" onClick={addRow}>
        + Добавить запись
      </button>
    </div>
  );
}


// ── Управление документами ────────────────────────────────────────────────────

function DocumentsTable({ documents, onDelete, onPreview, onDownload }) {
  if (!documents.length) {
    return <p className="text-sm text-slate-500">В системе ещё нет загруженных работ.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
            <th className="py-2 pr-3">Файл</th>
            <th className="py-2 pr-3">Автор</th>
            <th className="py-2 pr-3">Загружен</th>
            <th className="py-2 pr-3">Обработка</th>
            <th className="py-2 pr-3">Проверка</th>
            <th className="py-2 pr-3">Действия</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => (
            <tr key={doc.id} className="border-b border-slate-100 last:border-b-0 align-top">
              <td className="py-2 pr-3 font-medium break-words max-w-xs">
                {doc.original_filename}
                {doc.has_unresolved_violations && (
                  <span className="ml-1.5 inline-block text-[10px] font-medium px-1.5 py-0.5 rounded bg-amber-100 text-amber-800">
                    замечания
                  </span>
                )}
              </td>
              <td className="py-2 pr-3">
                {doc.owner_full_name ? (
                  <div>
                    <p className="text-sm break-words">{doc.owner_full_name}</p>
                    <p className="text-xs text-slate-500 break-all">{doc.owner_email}</p>
                  </div>
                ) : (
                  <span className="text-slate-400">—</span>
                )}
              </td>
              <td className="py-2 pr-3 text-xs text-slate-600 whitespace-nowrap">{formatDate(doc.uploaded_at)}</td>
              <td className="py-2 pr-3 text-xs">{STATUS_LABELS[doc.status] ?? doc.status}</td>
              <td className="py-2 pr-3 text-xs">
                {doc.approval_status ? (
                  <span className={`text-[10px] uppercase tracking-wide font-medium px-1.5 py-0.5 rounded ${APPROVAL_BADGE[doc.approval_status] ?? 'bg-gray-100 text-gray-600'}`}>
                    {APPROVAL_LABELS[doc.approval_status] ?? doc.approval_status}
                  </span>
                ) : (
                  <span className="text-slate-400">—</span>
                )}
              </td>
              <td className="py-2 pr-3">
                <div className="flex flex-wrap gap-1">
                  <button
                    type="button"
                    className="rounded-lg border border-slate-300 px-2 py-1 text-xs hover:bg-slate-50 disabled:opacity-40"
                    onClick={() => onPreview(doc.id)}
                    disabled={doc.status !== 'done'}
                  >
                    Просмотр
                  </button>
                  <button
                    type="button"
                    className="rounded-lg border border-slate-300 px-2 py-1 text-xs hover:bg-slate-50"
                    onClick={() => onDownload(doc.id, 'original', doc.original_filename)}
                  >
                    Оригинал
                  </button>
                  <button
                    type="button"
                    className="rounded-lg border border-slate-300 px-2 py-1 text-xs hover:bg-slate-50 disabled:opacity-40"
                    onClick={() => onDownload(doc.id, 'processed', `processed_${doc.original_filename}`)}
                    disabled={doc.status !== 'done'}
                  >
                    Обработанный
                  </button>
                  <button
                    type="button"
                    className="rounded-lg border border-rose-300 px-2 py-1 text-xs text-rose-600 hover:bg-rose-50"
                    onClick={() => onDelete(doc)}
                  >
                    Удалить
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


// ── Управление пользователями ─────────────────────────────────────────────────

function UsersTable({ users, onRoleChange }) {
  if (!users.length) {
    return <p className="text-sm text-slate-500">Пользователей нет.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
            <th className="py-2 pr-3">Имя</th>
            <th className="py-2 pr-3">Email</th>
            <th className="py-2 pr-3">Роль</th>
            <th className="py-2 pr-3">Зарегистрирован</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id} className="border-b border-slate-100 last:border-b-0 align-middle">
              <td className="py-2 pr-3 font-medium break-words max-w-xs">{u.full_name}</td>
              <td className="py-2 pr-3 break-all text-slate-600 max-w-xs">{u.email}</td>
              <td className="py-2 pr-3">
                <select
                  className="input py-1 text-xs"
                  value={u.role}
                  onChange={(e) => onRoleChange(u.id, e.target.value)}
                >
                  {Object.entries(ROLE_LABELS).map(([val, label]) => (
                    <option key={val} value={val}>{label}</option>
                  ))}
                </select>
              </td>
              <td className="py-2 pr-3 text-xs text-slate-500 whitespace-nowrap">{formatDate(u.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


// ── Редактор нормативной конфигурации ─────────────────────────────────────────

function ConfigEditor({ rulesObj, onPatch, showRaw, rulesJson, onJsonEdit, rulesJsonError }) {
  const meta = rulesObj.meta ?? {};
  const page = rulesObj.page_settings ?? {};
  const body = rulesObj.body_text_style ?? {};
  const heading = rulesObj.heading_detection ?? {};
  const volume = rulesObj.volume_limits ?? {};
  const structural = rulesObj.structural_elements ?? {};
  const numbering = rulesObj.numbering_rules ?? {};
  const captionStyle = rulesObj.caption_style ?? {};
  const reports = rulesObj.report_templates ?? {};
  const security = rulesObj.security ?? {};
  const forbidden = rulesObj.forbidden_heading_map ?? {};

  const patchSection = (key, updates) => {
    onPatch({ ...rulesObj, [key]: { ...(rulesObj[key] ?? {}), ...updates } });
  };
  const setTopLevel = (key, v) => {
    onPatch({ ...rulesObj, [key]: v });
  };

  if (showRaw) {
    return (
      <div className="space-y-2">
        {rulesJsonError && <p className="text-xs text-rose-600">{rulesJsonError}</p>}
        <textarea
          className="input min-h-[60vh] font-mono text-xs"
          value={rulesJson}
          onChange={(e) => onJsonEdit(e.target.value)}
        />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <details open className="rounded-xl border border-slate-200 bg-white p-4">
        <summary className="cursor-pointer text-sm font-semibold text-slate-700">Метаданные базы</summary>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <TextField label="Название" value={meta.name} onChange={(v) => patchSection('meta', { name: v })} />
          <TextField label="Версия" value={meta.version} onChange={(v) => patchSection('meta', { version: v })} />
          <TextField label="Дата вступления в силу" value={meta.effective_date} onChange={(v) => patchSection('meta', { effective_date: v })} placeholder="YYYY-MM-DD" />
          <TextField label="Ссылка / приказ" value={meta.reference} onChange={(v) => patchSection('meta', { reference: v })} />
        </div>
      </details>

      <details className="rounded-xl border border-slate-200 bg-white p-4">
        <summary className="cursor-pointer text-sm font-semibold text-slate-700">Параметры страницы</summary>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <SelectField
            label="Формат бумаги"
            value={page.paper}
            options={[{ value: 'A4', label: 'A4' }, { value: 'A5', label: 'A5' }, { value: 'Letter', label: 'Letter' }]}
            onChange={(v) => patchSection('page_settings', { paper: v })}
          />
          <SelectField
            label="Ориентация"
            value={page.orientation}
            options={[{ value: 'portrait', label: 'Книжная' }, { value: 'landscape', label: 'Альбомная' }]}
            onChange={(v) => patchSection('page_settings', { orientation: v })}
          />
          <NumberField label="Левое поле (мм)" value={page.margin_left_mm} onChange={(v) => patchSection('page_settings', { margin_left_mm: v })} />
          <NumberField label="Правое поле (мм)" value={page.margin_right_mm} onChange={(v) => patchSection('page_settings', { margin_right_mm: v })} />
          <NumberField label="Верхнее поле (мм)" value={page.margin_top_mm} onChange={(v) => patchSection('page_settings', { margin_top_mm: v })} />
          <NumberField label="Нижнее поле (мм)" value={page.margin_bottom_mm} onChange={(v) => patchSection('page_settings', { margin_bottom_mm: v })} />
        </div>
      </details>

      <details className="rounded-xl border border-slate-200 bg-white p-4">
        <summary className="cursor-pointer text-sm font-semibold text-slate-700">Основной текст</summary>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <TextField label="Шрифт" value={body.font_name} onChange={(v) => patchSection('body_text_style', { font_name: v })} placeholder="Times New Roman" />
          <NumberField label="Размер (pt)" value={body.font_size_pt} onChange={(v) => patchSection('body_text_style', { font_size_pt: v })} step={0.5} />
          <NumberField label="Межстрочный интервал" value={body.line_spacing} onChange={(v) => patchSection('body_text_style', { line_spacing: v })} step={0.1} />
          <NumberField label="Абзацный отступ (см)" value={body.first_line_indent_cm} onChange={(v) => patchSection('body_text_style', { first_line_indent_cm: v })} step={0.05} />
          <SelectField
            label="Выравнивание"
            value={body.alignment}
            options={[
              { value: 'justify', label: 'По ширине' },
              { value: 'left', label: 'По левому краю' },
              { value: 'right', label: 'По правому краю' },
              { value: 'center', label: 'По центру' },
            ]}
            onChange={(v) => patchSection('body_text_style', { alignment: v })}
          />
          <TextField label="Цвет (HEX)" value={body.font_color} onChange={(v) => patchSection('body_text_style', { font_color: v })} placeholder="000000" />
          <NumberField label="Пробел до (pt)" value={body.space_before_pt} onChange={(v) => patchSection('body_text_style', { space_before_pt: v })} />
          <NumberField label="Пробел после (pt)" value={body.space_after_pt} onChange={(v) => patchSection('body_text_style', { space_after_pt: v })} />
        </div>
      </details>

      <details className="rounded-xl border border-slate-200 bg-white p-4">
        <summary className="cursor-pointer text-sm font-semibold text-slate-700">Детектор заголовков</summary>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <NumberField label="Макс. длина (симв.)" value={heading.max_length} onChange={(v) => patchSection('heading_detection', { max_length: v })} />
          <NumberField label="Макс. слов" value={heading.max_words} onChange={(v) => patchSection('heading_detection', { max_words: v })} />
          <NumberField label="Порог скачка шрифта (pt)" value={heading.font_jump_pt} onChange={(v) => patchSection('heading_detection', { font_jump_pt: v })} step={0.5} />
          <NumberField label="Порог длины соседа" value={heading.neighbour_long_threshold} onChange={(v) => patchSection('heading_detection', { neighbour_long_threshold: v })} />
        </div>
      </details>

      <details className="rounded-xl border border-slate-200 bg-white p-4">
        <summary className="cursor-pointer text-sm font-semibold text-slate-700">Структурные элементы</summary>
        <p className="mt-1 mb-3 text-xs text-slate-500">Синонимы (по одному на строке), которые алгоритм распознаёт как соответствующий тип раздела.</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <ArrayTextarea label="Титульный лист" value={structural.title_page} onChange={(v) => patchSection('structural_elements', { title_page: v })} />
          <ArrayTextarea label="Задание" value={structural.task} onChange={(v) => patchSection('structural_elements', { task: v })} />
          <ArrayTextarea label="Содержание" value={structural.contents} onChange={(v) => patchSection('structural_elements', { contents: v })} />
          <ArrayTextarea label="Введение" value={structural.introduction} onChange={(v) => patchSection('structural_elements', { introduction: v })} />
          <ArrayTextarea label="Заключение" value={structural.conclusion} onChange={(v) => patchSection('structural_elements', { conclusion: v })} />
          <ArrayTextarea label="Список источников" value={structural.references} onChange={(v) => patchSection('structural_elements', { references: v })} />
          <ArrayTextarea label="Термины и сокращения" value={structural.terms} onChange={(v) => patchSection('structural_elements', { terms: v })} />
          <TextField label="Regex приложения" value={structural.appendix_regex} onChange={(v) => patchSection('structural_elements', { appendix_regex: v })} placeholder="^приложение\s+[а-яёa-z]" />
        </div>
      </details>

      <details className="rounded-xl border border-slate-200 bg-white p-4">
        <summary className="cursor-pointer text-sm font-semibold text-slate-700">Запрещённые заголовки</summary>
        <p className="mt-1 mb-3 text-xs text-slate-500">Ключ — запрещённое название. Значение пустое — удалить, иначе — заменить на указанный текст.</p>
        <KeyValueEditor
          label=""
          value={forbidden}
          onChange={(v) => setTopLevel('forbidden_heading_map', v)}
          keyPlaceholder="обзор литературы"
          valuePlaceholder="СОДЕРЖАНИЕ (или пусто)"
        />
      </details>

      <details className="rounded-xl border border-slate-200 bg-white p-4">
        <summary className="cursor-pointer text-sm font-semibold text-slate-700">Нумерация</summary>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <SelectField
            label="Режим нумерации рисунков"
            value={numbering.figure_mode}
            options={[
              { value: 'continuous', label: 'Сквозная' },
              { value: 'by_chapter', label: 'По главам' },
            ]}
            onChange={(v) => patchSection('numbering_rules', { figure_mode: v })}
          />
          <SelectField
            label="Режим нумерации таблиц"
            value={numbering.table_mode}
            options={[
              { value: 'continuous', label: 'Сквозная' },
              { value: 'by_chapter', label: 'По главам' },
            ]}
            onChange={(v) => patchSection('numbering_rules', { table_mode: v })}
          />
          <SelectField
            label="Режим нумерации листингов"
            value={numbering.listing_mode}
            options={[
              { value: 'continuous', label: 'Сквозная' },
              { value: 'by_chapter', label: 'По главам' },
            ]}
            onChange={(v) => patchSection('numbering_rules', { listing_mode: v })}
          />
          <CheckboxField
            label="Проверять последовательность цитирований"
            value={numbering.validate_citation_sequence}
            onChange={(v) => patchSection('numbering_rules', { validate_citation_sequence: v })}
          />
        </div>
      </details>

      <details className="rounded-xl border border-slate-200 bg-white p-4">
        <summary className="cursor-pointer text-sm font-semibold text-slate-700">Подписи к рисункам и таблицам</summary>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <NumberField
            label="Абзацный отступ строки таблицы (см)"
            value={captionStyle.table_first_line_indent_cm}
            onChange={(v) => patchSection('caption_style', { table_first_line_indent_cm: v })}
            step={0.05}
            min={0}
            hint='Legacy-поле: в обработке всегда применяется 0 см (без отступа).'
          />
        </div>
      </details>

      <details className="rounded-xl border border-slate-200 bg-white p-4">
        <summary className="cursor-pointer text-sm font-semibold text-slate-700">Объём бакалаврской работы</summary>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <NumberField label="Минимум страниц" value={volume.min} onChange={(v) => patchSection('volume_limits', { min: v })} min={0} />
          <NumberField label="Максимум страниц" value={volume.max} onChange={(v) => patchSection('volume_limits', { max: v })} min={0} />
        </div>
      </details>

      <details className="rounded-xl border border-slate-200 bg-white p-4">
        <summary className="cursor-pointer text-sm font-semibold text-slate-700">Тексты отчёта и хранение</summary>
        <div className="mt-3 grid gap-3">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-slate-600">Предупреждение о TOC</span>
            <textarea
              className="input min-h-[70px] text-sm"
              value={reports.warning_toc ?? ''}
              onChange={(e) => patchSection('report_templates', { warning_toc: e.target.value })}
            />
          </label>
          <NumberField
            label="Срок хранения документов (дней)"
            value={security.retention_days}
            onChange={(v) => patchSection('security', { retention_days: v })}
            min={1}
          />
        </div>
      </details>
    </div>
  );
}


// ── Главная страница ──────────────────────────────────────────────────────────

function AdminPage() {
  const [activeView, setActiveView] = useState('overview');

  const [users, setUsers] = useState([]);
  const [stats, setStats] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [versions, setVersions] = useState([]);
  const [selectedVersion, setSelectedVersion] = useState('');
  const [rulesObj, setRulesObj] = useState({});
  const [rulesJson, setRulesJson] = useState('{}');
  const [rulesJsonError, setRulesJsonError] = useState('');
  const [showRawJson, setShowRawJson] = useState(false);
  const [toast, setToast] = useState('');

  // Фильтры раздела «Работы»
  const [docQuery, setDocQuery] = useState('');
  const [docStatusFilter, setDocStatusFilter] = useState('all');
  const [docSort, setDocSort] = useState('date');

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(''), 3500);
  };

  const loadAll = async () => {
    const [usersRes, statsRes, versionsRes, docsRes] = await Promise.all([
      api.get('/admin/users'),
      api.get('/admin/stats'),
      api.get('/normative/versions'),
      api.get('/documents/'),
    ]);
    setUsers(usersRes.data);
    setStats(statsRes.data);
    setVersions(versionsRes.data);
    setDocuments(docsRes.data);
    if (versionsRes.data.length > 0 && !selectedVersion) {
      setSelectedVersion(versionsRes.data[0].id);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  useEffect(() => {
    if (!selectedVersion) return;
    api.get(`/normative/${selectedVersion}/rules`).then((response) => {
      const cfg = response.data.rules_config ?? {};
      setRulesObj(cfg);
      setRulesJson(JSON.stringify(cfg, null, 2));
      setRulesJsonError('');
    });
  }, [selectedVersion]);

  const activeVersionName = useMemo(
    () => versions.find((v) => v.id === selectedVersion)?.name ?? '',
    [versions, selectedVersion],
  );

  const visibleDocuments = useMemo(() => {
    const q = docQuery.trim().toLowerCase();
    let list = documents.filter((d) => {
      if (docStatusFilter !== 'all' && (d.approval_status ?? '') !== docStatusFilter) return false;
      if (!q) return true;
      return (
        (d.original_filename || '').toLowerCase().includes(q) ||
        (d.owner_full_name || '').toLowerCase().includes(q) ||
        (d.owner_email || '').toLowerCase().includes(q)
      );
    });
    list = [...list];
    const ts = (d) => (d.uploaded_at ? new Date(d.uploaded_at).getTime() : 0);
    if (docSort === 'name') {
      list.sort((a, b) => (a.original_filename || '').localeCompare(b.original_filename || '', 'ru'));
    } else if (docSort === 'status') {
      const rank = (d) => (d.approval_status === 'pending_review' ? 0 : 1);
      list.sort((a, b) => rank(a) - rank(b) || ts(b) - ts(a));
    } else {
      list.sort((a, b) => ts(b) - ts(a));
    }
    return list;
  }, [documents, docQuery, docStatusFilter, docSort]);

  const applyPatch = (nextObj) => {
    setRulesObj(nextObj);
    setRulesJson(JSON.stringify(nextObj, null, 2));
    setRulesJsonError('');
  };

  const onJsonEdit = (value) => {
    setRulesJson(value);
    try {
      const parsed = JSON.parse(value);
      setRulesObj(parsed);
      setRulesJsonError('');
    } catch (err) {
      setRulesJsonError('JSON невалиден: ' + (err.message ?? ''));
    }
  };

  const saveRules = async () => {
    if (!selectedVersion) {
      showToast('Нет выбранной нормативной базы');
      return;
    }
    if (rulesJsonError) {
      showToast('Сначала исправьте JSON');
      return;
    }
    try {
      await api.put(`/admin/normative/${selectedVersion}/rules`, { rules_config: rulesObj });
      showToast('Нормативная база сохранена');
      await loadAll();
    } catch (err) {
      showToast('Ошибка сохранения: ' + (err?.response?.data?.detail ?? err.message));
    }
  };

  const handlePreview = async (docId) => {
    // window.open() на preview-endpoint открывает новую вкладку БЕЗ
    // заголовка авторизации, в результате получаем {"detail":"Not
    // authenticated"}. Тянем через axios (он подставляет bearer-токен) и
    // открываем blob в новой вкладке.
    try {
      const response = await api.get(`/documents/${docId}/preview/processed`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }));
      const win = window.open(url, '_blank', 'noopener');
      if (!win) showToast('Браузер блокирует всплывающее окно с превью');
      // Освобождаем blob через минуту — новой вкладке хватит времени, чтобы PDF подгрузился.
      setTimeout(() => window.URL.revokeObjectURL(url), 60_000);
    } catch (err) {
      const detail = err?.response?.status === 404
        ? 'PDF превью ещё не готово'
        : (err?.response?.data?.detail ?? err.message);
      showToast('Не удалось открыть превью: ' + detail);
    }
  };

  const handleDownload = async (docId, kind, filename) => {
    try {
      const response = await api.get(`/documents/${docId}/download/${kind}`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(response.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      showToast('Ошибка скачивания: ' + (err?.response?.data?.detail ?? err.message));
    }
  };

  const handleDelete = async (doc) => {
    if (!window.confirm(`Удалить «${doc.original_filename}» безвозвратно?`)) return;
    try {
      await api.delete(`/documents/${doc.id}`);
      showToast('Документ удалён');
      setDocuments((prev) => prev.filter((d) => d.id !== doc.id));
    } catch (err) {
      showToast('Ошибка удаления: ' + (err?.response?.data?.detail ?? err.message));
    }
  };

  const handleRoleChange = async (userId, newRole) => {
    try {
      const { data } = await api.patch(`/admin/users/${userId}`, { role: newRole });
      setUsers((prev) => prev.map((u) => (u.id === userId ? data : u)));
      showToast(`Роль обновлена: ${ROLE_LABELS[newRole] ?? newRole}`);
    } catch (err) {
      showToast('Ошибка: ' + (err?.response?.data?.detail ?? err.message));
      await loadAll();
    }
  };

  return (
    <Layout navItems={ADMIN_NAV_ITEMS} activeView={activeView} onNavChange={setActiveView}>
      {toast && (
        <div className="fixed right-6 top-20 z-50 rounded-xl bg-slate-800 px-4 py-2 text-sm text-white shadow-lg">
          {toast}
        </div>
      )}

      {activeView === 'overview' && (
        <div className="overflow-auto h-full">
          <DashboardView
            stats={stats}
            title="Обзор"
            activeVersionName={activeVersionName}
            onUsersClick={() => setActiveView('users')}
          />
          <div className="px-8 pb-8 space-y-6">
            {/* Статистика */}
            <div className="card">
              <h2 className="mb-4 text-lg font-semibold">Статистика</h2>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <div className="rounded-xl border border-slate-200 bg-white p-4">
                  <p className="text-xs text-slate-500 mb-1">Всего работ</p>
                  <p className="text-2xl font-bold text-slate-800">{stats?.total_documents ?? '—'}</p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-4">
                  <p className="text-xs text-slate-500 mb-1">Пользователей</p>
                  <p className="text-2xl font-bold text-slate-800">{stats?.total_users ?? '—'}</p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-4">
                  <p className="text-xs text-slate-500 mb-1">Ср. нарушений</p>
                  <p className="text-2xl font-bold text-slate-800">
                    {stats ? stats.avg_violations.toFixed(1) : '—'}
                  </p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-4">
                  <p className="text-xs text-slate-500 mb-1">На проверке</p>
                  <p className="text-2xl font-bold text-amber-600">
                    {documents.filter((d) => d.approval_status === 'pending_review').length}
                  </p>
                </div>
              </div>
              {activeVersionName && (
                <p className="mt-3 text-sm text-slate-500">
                  Активная нормативная база: <span className="font-medium text-slate-700">{activeVersionName}</span>
                </p>
              )}
            </div>

            {/* Быстрые ссылки */}
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                className="btn-primary"
                onClick={() => setActiveView('documents')}
              >
                К работам
              </button>
              <button
                type="button"
                className="rounded-lg border border-slate-300 px-4 py-2 text-sm hover:bg-slate-50"
                onClick={() => setActiveView('config')}
              >
                К конфигурации
              </button>
            </div>

            {/* Список студентов */}
            <div className="card">
              {(() => {
                const students = users.filter((u) => u.role === 'student');
                return (
                  <>
                    <h2 className="mb-4 text-lg font-semibold">
                      Студенты ({students.length})
                    </h2>
                    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                      {students.map((u) => (
                        <button
                          key={u.id}
                          type="button"
                          className="rounded-xl border border-slate-200 bg-white p-3 text-sm text-left hover:bg-slate-50 transition-colors"
                          onClick={() => setActiveView('users')}
                        >
                          <p className="font-medium break-words">{u.full_name}</p>
                          <p className="text-slate-500 break-all">{u.email}</p>
                        </button>
                      ))}
                      {students.length === 0 && (
                        <p className="text-slate-400 text-sm col-span-full">Студентов пока нет</p>
                      )}
                    </div>
                  </>
                );
              })()}
            </div>
          </div>
        </div>
      )}

      {activeView !== 'overview' && <div className="p-8 space-y-6 overflow-auto h-full">


        {activeView === 'users' && (
          <>
            <div className="flex items-center justify-between">
              <h1 className="text-2xl font-semibold text-gray-900">Пользователи ({users.length})</h1>
              <button type="button" className="rounded-lg border border-slate-300 px-3 py-1 text-xs hover:bg-slate-50" onClick={loadAll}>
                Обновить
              </button>
            </div>
            <section className="card">
              <p className="mb-4 text-xs text-slate-500">
                Чтобы изменить роль пользователя, выберите новую роль в выпадающем списке — изменение применяется сразу.
              </p>
              <UsersTable users={users} onRoleChange={handleRoleChange} />
            </section>
          </>
        )}

        {activeView === 'documents' && (
          <>
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <h1 className="text-2xl font-semibold text-gray-900">
                Загруженные работы
                <span className="ml-2 text-base font-normal text-slate-400">{visibleDocuments.length} из {documents.length}</span>
              </h1>
              <button type="button" className="rounded-lg border border-slate-300 px-3 py-1 text-xs hover:bg-slate-50" onClick={loadAll}>
                Обновить
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              <input
                type="text"
                value={docQuery}
                onChange={(e) => setDocQuery(e.target.value)}
                placeholder="Поиск: файл, студент или email"
                className="input py-1 px-2 text-xs flex-1 min-w-[200px]"
              />
              <select
                value={docStatusFilter}
                onChange={(e) => setDocStatusFilter(e.target.value)}
                className="input py-1 px-2 text-xs"
              >
                <option value="all">Все статусы проверки</option>
                <option value="pending_review">На проверке</option>
                <option value="approved">Принят</option>
                <option value="rejected">Отклонён</option>
                <option value="">Не отправлен</option>
              </select>
              <select
                value={docSort}
                onChange={(e) => setDocSort(e.target.value)}
                className="input py-1 px-2 text-xs"
              >
                <option value="date">По дате (новее)</option>
                <option value="status">По статусу проверки</option>
                <option value="name">По имени файла</option>
              </select>
            </div>
            <section className="card">
              <DocumentsTable
                documents={visibleDocuments}
                onPreview={handlePreview}
                onDownload={handleDownload}
                onDelete={handleDelete}
              />
            </section>
          </>
        )}

        {activeView === 'config' && (
          <>
            <h1 className="text-2xl font-semibold text-gray-900">Нормативная база</h1>
            <section className="card">
              <div className="mb-4 flex flex-wrap items-center gap-2">
                <select className="input max-w-xs" value={selectedVersion} onChange={(e) => setSelectedVersion(e.target.value)}>
                  {versions.map((v) => (
                    <option key={v.id} value={v.id}>{v.name}</option>
                  ))}
                </select>
                <button type="button" className="btn-primary" onClick={saveRules}>Сохранить правила</button>
                <label className="ml-auto flex items-center gap-2 text-sm text-slate-600">
                  <input type="checkbox" checked={showRawJson} onChange={(e) => setShowRawJson(e.target.checked)} />
                  Расширенный режим (raw JSON)
                </label>
              </div>

              <ConfigEditor
                rulesObj={rulesObj}
                onPatch={applyPatch}
                showRaw={showRawJson}
                rulesJson={rulesJson}
                onJsonEdit={onJsonEdit}
                rulesJsonError={rulesJsonError}
              />
            </section>
          </>
        )}
      </div>}
    </Layout>
  );
}

export default AdminPage;
