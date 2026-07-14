import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import api from '../api/client';
import PdfPane from '../components/PdfPane';
import Layout from '../components/Layout';
import ConflictReviewPage from './ConflictReviewPage';
import SnapshotHistory from '../components/SnapshotHistory';
import NormativeDocsButton from '../components/NormativeDocsButton';
import getApiErrorMessage from '../utils/errorMessage';
import { hasUnread, markSeen } from '../utils/unreadComments';
import { violationNeedle, ACTIVE_ONLY_ANCHOR_TYPES } from '../utils/violationAnchor';
import { sortViolations } from '../utils/violationOrder';
import {
  SEVERITY_RU,
  VIOLATION_STATUS_RU,
  humaniseSignal,
  violationTypeLabel,
} from '../utils/violationLabels';
import { fmtDate, fmtSize } from '../utils/format';
import { parseFilename, downloadBlob } from '../utils/download';
import {
  APPROVAL_BADGE as APPROVAL_BADGE_STUDENT,
  APPROVAL_LABELS as APPROVAL_LABELS_STUDENT,
  ROLE_LABELS_STUDENT,
} from '../utils/labels';

// ── Константы ─────────────────────────────────────────────────────────────────

const CUSTOM = '__custom__';

const NAV_ITEMS = [
  { id: 'documents', label: 'Моя работа' },
  { id: 'settings',  label: 'Настройки' }
];

const PROCESSING_STEPS = [
  { label: 'Конвертация входного формата',  min: 0,  max: 20  },
  { label: 'Парсинг структуры документа',   min: 20, max: 40  },
  { label: 'Применение правил оформления',  min: 40, max: 75  },
  { label: 'Генерация отчёта',              min: 75, max: 85  },
  { label: 'Формирование PDF-превью',       min: 85, max: 92  },
  { label: 'Сохранение результата',         min: 92, max: 100 }
];

// Базовые метки по статусу документа. Для done используем docStatusLabel().
const STATUS_LABEL = {
  pending:    'Ожидание',
  processing: 'Обработка',
  done:       'Обработан',
  error:      'Ошибка'
};

const STATUS_BADGE = {
  pending:          'badge-pending',
  processing:       'badge-processing',
  done:             'badge-done',
  done_violations:  'badge-warning',   // done + есть незакрытые замечания
  error:            'badge-error'
};

// Возвращает человекочитаемый статус с учётом approval и замечаний.
function docStatusLabel(doc) {
  if (doc.approval_status === 'pending_review') return 'Отправлен';
  if (doc.approval_status === 'approved')       return 'Принят';
  if (doc.approval_status === 'rejected')       return 'Отклонён';
  if (doc.status === 'done') {
    return doc.has_unresolved_violations ? 'Есть замечания' : 'Обработан';
  }
  return STATUS_LABEL[doc.status] ?? doc.status;
}

function docStatusBadge(doc) {
  if (doc.approval_status === 'pending_review') return 'badge-pending';
  if (doc.approval_status === 'approved')       return 'badge-done';
  if (doc.approval_status === 'rejected')       return 'badge-error';
  if (doc.status === 'done' && doc.has_unresolved_violations) return STATUS_BADGE.done_violations;
  return STATUS_BADGE[doc.status] ?? 'badge-pending';
}

// ── Хелперы ───────────────────────────────────────────────────────────────────

// Локальные алиасы под старые имена — call-site код не трогаем.
const parseFileNameFromHeaders = parseFilename;
const triggerDownload = downloadBlob;

const stepStatus = (step, doc) => {
  if (!doc) return 'pending';
  const p = doc.progress ?? 0;
  if (doc.status === 'done') return 'done';
  if (doc.status === 'error') return p >= step.max ? 'done' : p >= step.min ? 'error' : 'pending';
  if (p >= step.max) return 'done';
  if (p >= step.min) return 'active';
  return 'pending';
};

// ── Под-компоненты ────────────────────────────────────────────────────────────

function StepIndicator({ n, label, state }) {
  const icon = {
    done:    <svg className="w-4 h-4" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="8" fill="#10b981"/><path d="M5 8l2 2 4-4" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>,
    active:  <span className="w-4 h-4 rounded-full bg-brand-500 flex items-center justify-center text-white text-[9px] font-bold">{n}</span>,
    error:   <span className="w-4 h-4 rounded-full bg-red-500 flex items-center justify-center text-white text-[9px] font-bold">!</span>,
    pending: <span className="w-4 h-4 rounded-full border-2 border-gray-200" />
  }[state] ?? null;

  return (
    <div className="flex items-center gap-3 py-2.5">
      <span className="flex-shrink-0">{icon}</span>
      <span className={`text-sm ${state === 'active' ? 'text-gray-900 font-medium' : state === 'done' ? 'text-gray-700' : 'text-gray-400'}`}>
        {label}
      </span>
      {state === 'active' && (
        <span className="ml-auto text-xs text-brand-500 animate-pulse">Выполняется</span>
      )}
      {state === 'done' && (
        <span className="ml-auto text-xs text-gray-400">Выполнено</span>
      )}
    </div>
  );
}

// ── Зона загрузки файла ───────────────────────────────────────────────────────

function DropZone({ onFile }) {
  const [dragging, setDragging] = useState(false);
  const [chosen, setChosen] = useState(null);
  const inputRef = useRef(null);

  const pick = (file) => { if (file) { setChosen(file); onFile(file); } };

  const onDrop = (e) => {
    e.preventDefault(); setDragging(false);
    pick(e.dataTransfer.files[0]);
  };

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={[
        'rounded-xl border-2 border-dashed transition-colors flex flex-col items-center justify-center py-10 gap-3 cursor-pointer',
        dragging ? 'border-brand-500 bg-brand-50' : 'border-brand-300 bg-white hover:border-brand-400'
      ].join(' ')}
      onClick={() => inputRef.current?.click()}
    >
      <svg width="36" height="36" viewBox="0 0 36 36" fill="none">
        <path d="M18 24V12M18 12l-5 5M18 12l5 5" stroke="#3b82f6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        <rect x="3" y="3" width="30" height="30" rx="8" stroke="#93c5fd" strokeWidth="1.5"/>
      </svg>
      {chosen
        ? <p className="text-sm text-gray-700 font-medium">{chosen.name}</p>
        : <p className="text-sm text-gray-600">Перетащите файл или</p>}
      <button
        type="button"
        className="btn-primary px-5 py-1.5"
        onClick={(e) => { e.stopPropagation(); inputRef.current?.click(); }}
      >
        выберите файл
      </button>
      <p className="text-xs text-gray-400">.docx | не более 50 МБ</p>
      <input
        ref={inputRef}
        type="file"
        className="sr-only"
        accept=".docx"
        onChange={(e) => pick(e.target.files[0])}
      />
    </div>
  );
}

// ── Главная страница (Моя работа) ────────────────────────────────────────────

const HOW_IT_WORKS = [
  {
    icon: (
      <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
        <path d="M11 2v6m0 0l-3-3m3 3l3-3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
        <rect x="3" y="14" width="16" height="6" rx="2" stroke="currentColor" strokeWidth="1.6"/>
      </svg>
    ),
    step: '1',
    title: 'Загрузите файл',
    desc: 'Прикрепите .docx с вашей ВКР. Поддерживаются файлы до 50 МБ.',
  },
  {
    icon: (
      <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
        <circle cx="11" cy="11" r="8" stroke="currentColor" strokeWidth="1.6"/>
        <path d="M7.5 11l2.5 2.5 4.5-4.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    ),
    step: '2',
    title: 'Автоматическая проверка',
    desc: 'Сервис проверяет оформление по Приказу МИИГАиК №697-01 и ГОСТ 7.32 — шрифты, отступы, заголовки, ссылки.',
  },
  {
    icon: (
      <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
        <path d="M4 11h14M13 6l5 5-5 5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    ),
    step: '3',
    title: 'Получите исправленный файл',
    desc: 'Скачайте .docx с автоматически применёнными исправлениями и разбором оставшихся замечаний.',
  },
  {
    icon: (
      <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
        <circle cx="8" cy="7" r="3.5" stroke="currentColor" strokeWidth="1.6"/>
        <path d="M2 19c0-3.3 2.7-6 6-6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
        <path d="M15 13v6m3-3h-6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
      </svg>
    ),
    step: '4',
    title: 'Отправьте руководителю',
    desc: 'После устранения замечаний отправьте работу научному руководителю прямо через систему.',
  },
];

function DocumentsView({ documents, currentUser, onNavigateUpload, onUploadFile, onSelectDoc, onDownload, toast }) {
  const [uploadMode, setUploadMode] = useState('full');
  const [uploading, setUploading] = useState(false);
  const [showReupload, setShowReupload] = useState(false);
  const [docViolations, setDocViolations] = useState(null);

  const currentDoc = documents.length > 0 ? documents[0] : null;
  const hasDoc = currentDoc !== null;

  // Загружаем сводку нарушений для карточки
  useEffect(() => {
    if (!currentDoc?.id || currentDoc.status !== 'done') { setDocViolations(null); return; }
    api.get(`/violations/${currentDoc.id}`)
      .then((r) => setDocViolations(r.data))
      .catch(() => setDocViolations(null));
  }, [currentDoc?.id, currentDoc?.status]);

  const violationCounts = useMemo(() => {
    if (!docViolations) return null;
    return {
      critical:  docViolations.filter((v) => v.severity === 'critical'  && v.status === 'manual_required').length,
      warning:   docViolations.filter((v) => v.severity === 'warning'   && v.status === 'manual_required').length,
      autoFixed: docViolations.filter((v) => v.status === 'auto_fixed').length,
    };
  }, [docViolations]);

  // Хронология событий из данных документа
  const timeline = useMemo(() => {
    if (!currentDoc) return [];
    const events = [];
    if (currentDoc.uploaded_at)
      events.push({ label: 'Загружен', date: currentDoc.uploaded_at, color: 'bg-brand-500' });
    if (currentDoc.status === 'done' || currentDoc.status === 'error')
      events.push({ label: currentDoc.status === 'done' ? 'Обработан' : 'Ошибка обработки', date: currentDoc.uploaded_at, color: currentDoc.status === 'done' ? 'bg-emerald-500' : 'bg-red-500' });
    if (currentDoc.approval_status === 'pending_review')
      events.push({ label: 'Отправлен руководителю', date: null, color: 'bg-amber-400' });
    if (currentDoc.approval_status === 'approved')
      events.push({ label: 'Принят руководителем', date: null, color: 'bg-emerald-600' });
    if (currentDoc.approval_status === 'rejected')
      events.push({ label: 'Отклонён руководителем', date: null, color: 'bg-red-500' });
    return events;
  }, [currentDoc]);

  const handleFile = async (file) => {
    setUploading(true);
    try {
      const body = new FormData();
      body.append('file', file);
      body.append('mode', uploadMode);
      const res = await onUploadFile(body);
      setShowReupload(false);
      onNavigateUpload(res.data.document.id);
    } catch (e) {
      toast(getApiErrorMessage(e, 'Ошибка загрузки'));
    } finally {
      setUploading(false);
    }
  };

  const uploadForm = (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-4 mb-2">
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-600">Режим:</label>
          <select className="input w-auto" value={uploadMode} onChange={(e) => setUploadMode(e.target.value)}>
            <option value="full">С исправлением</option>
            <option value="check_only">Только проверка</option>
          </select>
        </div>
      </div>
      <DropZone onFile={handleFile} />
      {uploading && <p className="text-sm text-brand-600 animate-pulse">Загрузка файла…</p>}
    </div>
  );

  return (
    <div className="p-4 md:p-8 space-y-6 overflow-auto h-full">
      <h1 className="text-2xl font-semibold text-gray-900">Моя работа</h1>

      {/* Нет документа → форма загрузки */}
      {!hasDoc && (
        <div className="card p-6">
          <div className="flex items-start justify-between gap-4 mb-4">
            <p className="text-sm text-gray-500">Загрузите файл ВКР в формате .docx для проверки и исправления оформления.</p>
            <NormativeDocsButton />
          </div>
          {uploadForm}
        </div>
      )}

      {/* Есть документ → карточка */}
      {hasDoc && !showReupload && (
        <div className="card p-6 space-y-4 border-l-4 border-brand-600 bg-brand-50/30">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-10 h-10 rounded-xl bg-brand-600 flex items-center justify-center flex-shrink-0">
                <svg width="20" height="20" viewBox="0 0 16 16" fill="none">
                  <rect x="2" y="1" width="10" height="14" rx="2" fill="white" fillOpacity="0.9"/>
                  <path d="M10 1l4 4H10V1z" fill="white" fillOpacity="0.5"/>
                  <line x1="4" y1="8" x2="10" y2="8" stroke="#001a72" strokeWidth="1.2" strokeLinecap="round"/>
                  <line x1="4" y1="10.5" x2="8.5" y2="10.5" stroke="#001a72" strokeWidth="1.2" strokeLinecap="round"/>
                </svg>
              </div>
              <div className="min-w-0">
                <p className="font-semibold text-gray-900 truncate">{currentDoc.original_filename}</p>
                <p className="text-xs text-gray-400 mt-0.5">{fmtDate(currentDoc.uploaded_at)}</p>
              </div>
            </div>
            <span className={`${docStatusBadge(currentDoc)} shrink-0`}>{docStatusLabel(currentDoc)}</span>
          </div>

          {/* [1] Сводка замечаний */}
          {violationCounts && (
            <div className="flex flex-wrap gap-3 py-3 border-t border-gray-100">
              {violationCounts.critical > 0 && (
                <span className="inline-flex items-center gap-1.5 text-xs font-medium text-red-700 bg-red-50 rounded-full px-3 py-1">
                  <span className="w-2 h-2 rounded-full bg-red-500 shrink-0" />
                  Критических: {violationCounts.critical}
                </span>
              )}
              {violationCounts.warning > 0 && (
                <span className="inline-flex items-center gap-1.5 text-xs font-medium text-amber-700 bg-amber-50 rounded-full px-3 py-1">
                  <span className="w-2 h-2 rounded-full bg-amber-400 shrink-0" />
                  Предупреждений: {violationCounts.warning}
                </span>
              )}
              {violationCounts.autoFixed > 0 && (
                <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-700 bg-emerald-50 rounded-full px-3 py-1">
                  <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
                  Исправлено автоматически: {violationCounts.autoFixed}
                </span>
              )}
              {violationCounts.critical === 0 && violationCounts.warning === 0 && (
                <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-700 bg-emerald-50 rounded-full px-3 py-1">
                  <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
                  Замечаний не осталось
                </span>
              )}
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            <button className="btn-primary py-1.5 px-4 text-sm" onClick={() => onSelectDoc(currentDoc)}>
              Открыть
            </button>
            {currentDoc.status === 'done' && (
              <button className="btn-secondary py-1.5 px-4 text-sm" onClick={() => onDownload(currentDoc, 'processed')}>
                Скачать исправленный
              </button>
            )}
            <button
              className="btn-secondary py-1.5 px-4 text-sm ml-auto text-orange-600 border-orange-200 hover:bg-orange-50"
              onClick={() => setShowReupload(true)}
            >
              Загрузить новую версию
            </button>
          </div>
        </div>
      )}

      {/* Повторная загрузка */}
      {hasDoc && showReupload && (
        <div className="card p-6 space-y-3">
          <div className="flex items-center justify-between mb-1">
            <p className="font-medium text-gray-900">Загрузить новую версию</p>
            <button className="text-gray-400 hover:text-gray-600 text-sm" onClick={() => setShowReupload(false)}>Отмена</button>
          </div>
          <p className="text-xs text-gray-500">Предыдущая версия останется в системе и будет доступна администратору.</p>
          {uploadForm}
        </div>
      )}

      {/* Нижние блоки — в два столбца на широких экранах */}
      <div className="grid gap-6 md:grid-cols-2">

        {/* [2] Руководитель */}
        <div className="card p-5 space-y-2">
          <div className="flex items-center gap-2 mb-1">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="text-brand-600 shrink-0">
              <circle cx="6" cy="5" r="3" stroke="currentColor" strokeWidth="1.4"/>
              <path d="M1 14c0-2.8 2.2-5 5-5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
              <path d="M12 10v4m2-2h-4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
            </svg>
            <h2 className="font-semibold text-gray-900 text-sm">Научный руководитель</h2>
          </div>
          {currentUser?.supervisor_name ? (
            <p className="text-sm text-gray-700">{currentUser.supervisor_name}</p>
          ) : (
            <p className="text-sm text-gray-400 leading-relaxed">
              Руководитель ещё не назначен. Обратитесь к нему — он прикрепит вас в системе, и вы сможете отправить работу на проверку.
            </p>
          )}
        </div>

        {/* [4] Хронология */}
        {hasDoc && timeline.length > 0 && (
          <div className="card p-5">
            <div className="flex items-center gap-2 mb-3">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="text-brand-600 shrink-0">
                <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.4"/>
                <path d="M8 5v3.5l2 1.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              <h2 className="font-semibold text-gray-900 text-sm">История</h2>
            </div>
            <ol className="space-y-2">
              {timeline.map((e, i) => (
                <li key={i} className="flex items-center gap-3 text-sm">
                  <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${e.color}`} />
                  <span className="text-gray-700">{e.label}</span>
                  {e.date && <span className="text-gray-400 text-xs ml-auto">{fmtDate(e.date)}</span>}
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>

      {/* [3] Как это работает — всегда снизу */}
      <div className="card p-6">
        <h2 className="font-semibold text-gray-900 mb-5">Как это работает</h2>
        <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
          {HOW_IT_WORKS.map((s) => (
            <div key={s.step} className="flex gap-3">
              <div className="w-9 h-9 rounded-xl bg-brand-50 text-brand-600 flex items-center justify-center shrink-0">
                {s.icon}
              </div>
              <div>
                <p className="text-xs font-semibold text-brand-600 mb-0.5">Шаг {s.step}</p>
                <p className="text-sm font-medium text-gray-900 leading-snug">{s.title}</p>
                <p className="text-xs text-gray-500 mt-1 leading-relaxed">{s.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Экран обработки (Загрузить ВКР) ───────────────────────────────────────────

function ProcessingView({ doc, onCancel, onNavigateDocs, onViewResult, onUploadFile, toast }) {
  const [uploadMode, setUploadMode] = useState('full');
  const [uploading, setUploading] = useState(false);

  const handleFile = async (file) => {
    if (!onUploadFile) return;
    setUploading(true);
    try {
      const body = new FormData();
      body.append('file', file);
      body.append('mode', uploadMode);
      await onUploadFile(body);
    } catch (e) {
      toast?.(getApiErrorMessage(e, 'Ошибка загрузки'));
    } finally {
      setUploading(false);
    }
  };

  if (!doc) {
    return (
      <div className="p-4 md:p-8 space-y-6 overflow-auto h-full">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold text-gray-900">Загрузить ВКР</h1>
        </div>
        <div className="card p-6 space-y-3">
          <div className="flex flex-wrap items-center gap-4 mb-2">
            <div className="flex items-center gap-2">
              <label className="text-sm text-gray-600">Режим:</label>
              <select
                className="input w-auto"
                value={uploadMode}
                onChange={(e) => setUploadMode(e.target.value)}
              >
                <option value="full">С исправлением</option>
                <option value="check_only">Только проверка</option>
              </select>
            </div>
          </div>
          <DropZone onFile={handleFile} />
          {uploading && <p className="text-sm text-brand-600 animate-pulse">Загрузка файла…</p>}
        </div>
      </div>
    );
  }

  const isDone  = doc.status === 'done';
  const isError = doc.status === 'error';
  const isPending = doc.status === 'pending';
  const progress = doc.progress ?? 0;

  // Верхний индикатор шага (Загрузка / Обработка / Результат)
  const stageStep = isPending ? 1 : (isDone || isError) ? 3 : 2;

  return (
    <div className="p-4 md:p-8 space-y-6 overflow-auto h-full">
      {/* Шапка страницы */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl md:text-2xl font-semibold text-gray-900">Обработка документа</h1>
        <button className="text-sm text-gray-500 hover:text-gray-700" onClick={onNavigateDocs}>
          ← К списку
        </button>
      </div>

      {/* Прогресс по шагам */}
      <div className="card py-5 px-8 flex items-center gap-0">
        {['Загрузка', 'Обработка', 'Результат'].map((label, i) => {
          const step = i + 1;
          const done   = step < stageStep;
          const active = step === stageStep;
          return (
            <React.Fragment key={label}>
              <div className="flex flex-col items-center gap-1.5 min-w-[80px]">
                <div className={[
                  'w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold border-2 transition-all',
                  done   ? 'bg-emerald-500 border-emerald-500 text-white'
                         : active ? 'bg-brand-600 border-brand-600 text-white'
                                  : 'bg-white border-gray-200 text-gray-400'
                ].join(' ')}>
                  {done ? (
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                      <path d="M3 7l3 3 5-5" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  ) : step}
                </div>
                <span className={`text-xs font-medium ${active ? 'text-gray-900' : done ? 'text-gray-600' : 'text-gray-400'}`}>
                  {label}
                </span>
              </div>
              {i < 2 && (
                <div className={`flex-1 h-0.5 mx-1 ${done ? 'bg-emerald-400' : 'bg-gray-200'}`} />
              )}
            </React.Fragment>
          );
        })}
      </div>

      {/* Полоса с инфо о документе */}
      <div className="card py-3 px-5 flex items-center gap-4">
        <div className="w-10 h-10 rounded-lg bg-brand-50 flex items-center justify-center flex-shrink-0">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <rect x="3" y="2" width="12" height="16" rx="2" fill="#dbeafe"/>
            <path d="M13 2v4h4" fill="none"/>
            <path d="M13 2l4 4H13V2z" fill="#93c5fd"/>
          </svg>
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-gray-900 text-sm break-words">{doc.original_filename}</p>
          <p className="text-xs text-gray-500">
            {doc.original_format?.toUpperCase()} · загружен {fmtDate(doc.uploaded_at)}
          </p>
        </div>
      </div>

      {/* Шаги обработки + панель информации */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Шаги */}
        <div className="md:col-span-2 card space-y-1">
          <h3 className="font-semibold text-gray-900 mb-3">Этапы обработки</h3>
          <div className="divide-y divide-gray-50">
            {PROCESSING_STEPS.map((s, i) => (
              <StepIndicator
                key={s.label}
                n={i + 1}
                label={s.label}
                state={stepStatus(s, doc)}
              />
            ))}
          </div>

          {/* Прогресс-бар */}
          <div className="pt-4">
            <div className="flex items-center justify-between text-xs text-gray-500 mb-1.5">
              <span>Общий прогресс</span>
              {!isDone && !isError && (
                <span className="text-gray-400">Не закрывайте вкладку</span>
              )}
            </div>
            <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${isError ? 'bg-red-400' : 'bg-brand-500'}`}
                style={{ width: `${isDone ? 100 : progress}%` }}
              />
            </div>
            <p className="text-xs text-gray-500 mt-1">{isDone ? 100 : progress}%</p>
          </div>
        </div>

        {/* Панель информации */}
        <div className="card space-y-4">
          <h3 className="font-semibold text-gray-900">Информация</h3>
          <dl className="space-y-3 text-sm">
            {[
              ['Файл',      doc.original_filename],
              ['Формат',    doc.original_format?.toUpperCase() ?? '—'],
              ['Норм. база', doc.normative_version_name ?? '—'],
              ['Статус',    docStatusLabel(doc)]
            ].map(([k, v]) => (
              <div key={k}>
                <dt className="text-xs text-gray-400 uppercase tracking-wide mb-0.5">{k}</dt>
                <dd className="text-gray-900 font-medium break-words">{v}</dd>
              </div>
            ))}
          </dl>

          {!isDone && !isError && (
            <button className="btn-danger w-full mt-2" onClick={onCancel}>
              Отменить обработку
            </button>
          )}
          {(isDone || isError) && (
            <button
              className="btn-primary w-full"
              onClick={isDone && onViewResult ? onViewResult : onNavigateDocs}
            >
              {isDone ? 'Посмотреть результат' : 'Вернуться к документам'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Экран детализации (нарушения) ─────────────────────────────────────────────

const SEVERITY_BADGE = {
  critical: 'bg-red-100 text-red-700',
  warning:  'bg-amber-100 text-amber-700',
  info:     'bg-emerald-100 text-emerald-700',
};


// Русские словари названий/причин — в общем модуле utils/violationLabels.js
// (переиспользуется и StaffPage). SEVERITY_BADGE выше — это CSS-классы, не
// подписи, поэтому остаётся локально.

// APPROVAL_*, ROLE_LABELS_STUDENT — переехали в utils/labels (см. импорты выше).


function DetailView({ doc, violations, currentUser, onDownload, onApplyAction, onFixHeadingNumber, onDemoteHeading, onPromoteToHeading, onRevertCaption, onRevertAutoFix, onOpenConflictReview, onSubmitForReview, onRollback, onBack }) {
  const [activeMobileTab, setActiveMobileTab] = useState('violations'); // 'violations' | 'pdf'
  const [activeId, setActiveId]               = useState(null);
  const [showSplit, setShowSplit]             = useState(false); // режим До/После
  const [chosenNumbers, setChosenNumbers]     = useState({});
  const [customInlineNumbers, setCustomInlineNumbers] = useState({});
  // Введённые вручную номера для promote-to-heading (по violation.id).
  const [promoteNumbers, setPromoteNumbers] = useState({});
  const [pdfVersion, setPdfVersion]       = useState(0);
  // Финализация TOC + регенерация превью идут в фоне (мгновенный отклик на
  // правку, ~10–15 с на рендеры). Не угадываем таймером, а опрашиваем
  // report/meta: как только processed_pdf_storage_path сменился (фон
  // дорисовал новое превью) — обновляем превью ровно один раз.
  const previewPollRef = useRef(0);
  const [previewRefreshing, setPreviewRefreshing] = useState(false);
  // Текст заголовка, к которому нужно проскроллить после обновления превью.
  // Устанавливается при фиксе номера заголовка, сбрасывается через 5 с.
  const [postFixScrollText, setPostFixScrollText] = useState(null);
  const postFixClearRef = useRef(null);
  const bustPreview = useCallback((scrollTarget = null) => {
    setPreviewRefreshing(true);
    const token = ++previewPollRef.current;
    let baseline;
    // Агрессивный старт: первые попытки раз в 700 мс, потом экспоненциальный
    // откат до 3 с. LO конвертирует 7–12 с, хотим поймать готовность быстро.
    const nextDelay = (attempt) => {
      if (attempt < 5)  return 700;
      if (attempt < 12) return 1500;
      return 3000;
    };
    const tick = async (attempt) => {
      if (token !== previewPollRef.current) return; // началась новая правка
      try {
        const { data } = await api.get(`/documents/${doc.id}/report/meta`);
        const path = data?.processed_pdf_storage_path ?? null;
        if (baseline === undefined) {
          baseline = path; // фон ещё не начал — это «старый» путь
        } else if (path && path !== baseline) {
          if (token === previewPollRef.current) {
            setPdfVersion((n) => n + 1); // только теперь, когда PDF готов
            setPreviewRefreshing(false);
            if (scrollTarget) {
              if (postFixClearRef.current) clearTimeout(postFixClearRef.current);
              setPostFixScrollText(scrollTarget);
              postFixClearRef.current = window.setTimeout(
                () => setPostFixScrollText(null), 5000,
              );
            }
          }
          return; // фон дорисовал — вышли
        }
      } catch {
        /* меты ещё нет / сетевой сбой — просто повторим */
      }
      if (attempt < 50) {
        window.setTimeout(() => tick(attempt + 1), nextDelay(attempt));
      } else {
        // Таймаут ~2.5 мин: фон не ответил (LO недоступен?) — снимаем спиннер.
        if (token === previewPollRef.current) setPreviewRefreshing(false);
      }
    };
    window.setTimeout(() => tick(0), 300);
  }, [doc.id]);
  const [showHistory, setShowHistory]     = useState(false);
  const [openDropdown, setOpenDropdown]   = useState(null); // 'download' | 'report' | null
  const [dropdownRect, setDropdownRect]   = useState(null);
  const downloadBtnRef                    = useRef(null);
  const [panelWidth, setPanelWidth]       = useState(384);  // px, начальное значение = w-96
  const dragRef                           = useRef(null);
  // ID нарушения, по которому сейчас летит запрос. Блокирует все
  // конфликт-кнопки до завершения, потому что каскад на бэке делает
  // DELETE+INSERT всех heading_number_conflict — старые ID после первого
  // клика становятся невалидными, и второй параллельный клик ловит 404
  // "violation not found".
  const [applyingId, setApplyingId]       = useState(null);
  const [expandedCascade, setExpandedCascade] = useState(() => new Set());
  const [filterSeverity, setFilterSeverity]   = useState('all');
  const [filterStatus, setFilterStatus]       = useState('manual_required');
  const violationRefs                     = useRef({});

  // Коммуникация: история раундов + тред
  const [reviewHistory, setReviewHistory] = useState([]);
  const [comments, setComments]           = useState([]);
  const [showChat, setShowChat]           = useState(false);
  const [chatText, setChatText]           = useState('');
  const [chatBusy, setChatBusy]           = useState(false);
  const chatBottomRef                     = useRef(null);

  useEffect(() => {
    setReviewHistory([]);
    setComments([]);
    setShowChat(false);
    // AbortController — если пользователь быстро переключает документ,
    // ответ старого запроса может прийти после нового и затереть state
    // данными от чужого документа. signal обрывает их на лету.
    const abort = new AbortController();
    api.get(`/documents/${doc.id}/review-history`, { signal: abort.signal })
      .then((r) => setReviewHistory(r.data))
      .catch((e) => { if (e?.code !== 'ERR_CANCELED' && e?.name !== 'CanceledError') { /* ignore */ } });
    api.get(`/documents/${doc.id}/comments`, { signal: abort.signal })
      .then((r) => setComments(r.data))
      .catch((e) => { if (e?.code !== 'ERR_CANCELED' && e?.name !== 'CanceledError') { /* ignore */ } });
    return () => abort.abort();
  }, [doc.id]);

  useEffect(() => {
    if (showChat) chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [comments, showChat]);

  const sendChat = async () => {
    const body = chatText.trim();
    if (!body) return;
    setChatBusy(true);
    try {
      await api.post(`/documents/${doc.id}/comments`, { body });
      setChatText('');
      const r = await api.get(`/documents/${doc.id}/comments`);
      setComments(r.data);
    } catch {
      // ignore
    } finally {
      setChatBusy(false);
    }
  };

  const activeViolation = violations.find((v) => v.id === activeId);
  // Предпочитаем section_title — у heading_number_conflict original_text
  // содержит только голый номер ("1"), который совпадает со многими
  // местами в PDF и подсвечивает неверно. section_title несёт полную
  // строку заголовка.
  // violationNeedle для caption_renumbered/auto_fixed вернёт fixed_text —
  // в исправленном PDF старого текста подписи уже нет.
  const activeText = useMemo(
    () => violationNeedle(activeViolation),
    [activeViolation],
  );

  // Скроллим панель нарушений к активной карточке при смене activeId.
  useEffect(() => {
    if (activeId && violationRefs.current[activeId]) {
      violationRefs.current[activeId].scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [activeId]);

  const allHighlightTexts = useMemo(
    () => violations
      // Заголовки больше НЕ исключаем: PdfPane пропускает регион оглавления
      // (skipOnToc) и подсвечивает реальный абзац в теле, а не строку TOC.
      // Ссылки «[N]» (ACTIVE_ONLY) в постоянный список не кладём — они
      // подсвечиваются только когда выбрана их карточка (через activeText).
      .filter(
        (v) => v.status === 'manual_required'
          && !ACTIVE_ONLY_ANCHOR_TYPES.has(v.type),
      )
      .map((v) => violationNeedle(v))
      .filter(Boolean),
    [violations],
  );

  // Сбрасываем активный выбор, если активное нарушение исчезло из списка
  // ИЛИ только что перешло из manual_required в решённое (пользователь
  // нажал «Ознакомлен»/«Это не заголовок»/исправил). Без этого красное
  // активное подчёркивание в превью висело до перехода к след. замечанию.
  // Клик по уже-решённому info-нарушению (просмотр) не сбрасывается —
  // там нет перехода manual_required → решено (статус не менялся).
  const activeStatusRef = useRef(null);
  useEffect(() => {
    if (!activeId) { activeStatusRef.current = null; return; }
    const v = violations.find((v) => v.id === activeId);
    if (!v) { setActiveId(null); activeStatusRef.current = null; return; }
    const prev = activeStatusRef.current;
    activeStatusRef.current = v.status;
    if (prev === 'manual_required' && v.status !== 'manual_required') {
      setActiveId(null);
    }
  }, [violations, activeId]);

  const sortedViolations = useMemo(
    () => sortViolations(violations),
    [violations],
  );

  const unresolvedCount = useMemo(
    () => violations.filter((v) => v.status === 'manual_required').length,
    [violations],
  );
  const hasSupervisor = Boolean(currentUser?.supervisor_id);

  // Группируем cascade-дочерние heading_number_conflict под корневым нарушением,
  // чтобы пользователь не видел один и тот же вид ошибки N раз подряд.
  const activeViolations = useMemo(
    () => sortedViolations.filter((v) => {
      if (filterStatus !== 'all' && v.status !== filterStatus) return false;
      if (filterSeverity !== 'all' && v.severity !== filterSeverity) return false;
      return true;
    }),
    [sortedViolations, filterStatus, filterSeverity],
  );

  const groupedViolations = useMemo(() => {
    const hnList  = activeViolations.filter((v) => v.type === 'heading_number_conflict');
    const others  = activeViolations.filter((v) => v.type !== 'heading_number_conflict');
    const roots   = new Map(); // paragraph_index → violation
    const childOf = new Map(); // root_paragraph_index → [children]
    for (const v of hnList) {
      if (v.caused_by_index == null) {
        roots.set(v.paragraph_index, v);
      } else {
        const arr = childOf.get(v.caused_by_index) ?? [];
        arr.push(v);
        childOf.set(v.caused_by_index, arr);
      }
    }
    const items = [];
    for (const v of hnList) {
      if (v.caused_by_index != null) continue; // добавим под своим корнем
      items.push({ kind: 'hn_group', root: v, children: childOf.get(v.paragraph_index) ?? [] });
    }
    for (const v of hnList) {
      if (v.caused_by_index == null) continue;
      if (!roots.has(v.caused_by_index)) items.push({ kind: 'single', v }); // осиротевший
    }
    for (const v of others) items.push({ kind: 'single', v });
    return items;
  }, [activeViolations]);

  const pdfUrl = useMemo(
    () => `/api/v1/documents/${doc.id}/preview/processed?v=${pdfVersion}`,
    [doc.id, pdfVersion],
  );

  const originalPdfUrl = `/api/v1/documents/${doc.id}/preview/original`;

  const openOriginalInline = async () => {
    try {
      const res = await api.get(`/documents/${doc.id}/preview/original`, { responseType: 'blob' });
      const blobUrl = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      const win = window.open(blobUrl, '_blank');
      // освобождаем blob-URL как только вкладка загрузилась (или через минуту)
      if (win) win.addEventListener('load', () => URL.revokeObjectURL(blobUrl), { once: true });
      else setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
    } catch {
      onDownload(doc, 'original');
    }
  };

  const onDividerMouseDown = (e) => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = panelWidth;
    const onMove = (ev) => {
      const delta = startX - ev.clientX;
      setPanelWidth(Math.min(700, Math.max(260, startW + delta)));
    };
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  const handleFixAndBustPreview = async (vid, num) => {
    if (applyingId) return;
    setApplyingId(vid);
    // Вычисляем новый текст заголовка (номер изменился, тело осталось) —
    // после обновления превью PdfPane проскроллит к нему автоматически.
    const viol = violations.find((v) => v.id === vid);
    let scrollTarget = null;
    if (viol?.section_title && num) {
      const origPrefix = (viol.original_text || '') + ' ';
      scrollTarget = viol.section_title.startsWith(origPrefix)
        ? num + ' ' + viol.section_title.slice(origPrefix.length)
        : viol.section_title;
    }
    try {
      await onFixHeadingNumber(vid, num);
      bustPreview(scrollTarget);
    } finally {
      setApplyingId(null);
    }
  };

  const handleRevertCaptionAndBustPreview = async (vid) => {
    if (applyingId) return;
    setApplyingId(vid);
    try {
      await onRevertCaption(vid);
      bustPreview();
    } finally {
      setApplyingId(null);
    }
  };

  const handleRevertAutoFixAndBustPreview = async (vid) => {
    if (applyingId) return;
    setApplyingId(vid);
    try {
      await onRevertAutoFix(vid);
      bustPreview();
    } finally {
      setApplyingId(null);
    }
  };

  const handleDemoteAndBustPreview = async (vid, asKind, { skipPreview = false } = {}) => {
    if (applyingId) return;
    setApplyingId(vid);
    try {
      await onDemoteHeading(vid, asKind);
      // Для heading_confirm + «обычный текст» бэкенд ничего не перерисовывает
      // (абзац и так был телом) — опрос превью был бы 60 с впустую.
      if (!skipPreview) bustPreview();
    } finally {
      setApplyingId(null);
    }
  };

  const handlePromoteAndBustPreview = async (vid) => {
    const raw = (promoteNumbers[vid] || '').trim();
    if (raw && !/^\d+(\.\d+){0,2}$/.test(raw)) {
      alert('Номер должен иметь вид 1, 1.2 или 1.2.3 (или быть пустым)');
      return;
    }
    await onPromoteToHeading(vid, raw || null);
    bustPreview();
  };

  const handleViolationClick = (v) => {
    // Сбрасываем постфиксный скролл: пользователь кликает на нарушение
    // намеренно, его цель важнее таймера после автофикса.
    if (postFixClearRef.current) clearTimeout(postFixClearRef.current);
    setPostFixScrollText(null);
    setActiveId((prev) => (prev === v.id ? null : v.id));
  };

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') setActiveId(null); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Шапка */}
      <div className="shrink-0 flex items-center gap-2 px-4 md:px-4 py-2 border-b bg-white dark:bg-[#1e1e1e] dark:border-[#3a3a3a]">
        <button className="text-sm text-gray-500 hover:text-gray-700 shrink-0" onClick={onBack}>← К документам</button>
        <div className="min-w-0 flex-shrink mx-1">
          <h1 className="text-sm font-semibold text-gray-900 truncate">{doc.original_filename}</h1>
        </div>
        <span className={`${docStatusBadge(doc)} shrink-0`}>{docStatusLabel(doc)}</span>

        {/* Кнопки действий — правая часть шапки */}
        <div className="ml-auto flex items-center gap-1.5 shrink-0">
          <button className="btn-secondary text-xs py-1 px-2" onClick={openOriginalInline}>Оригинал</button>
          <button
            className={`btn-secondary text-xs py-1 px-2 ${showSplit ? 'ring-2 ring-brand-400 bg-brand-50' : ''}`}
            onClick={() => setShowSplit((v) => !v)}
          >
            {showSplit ? 'Один экран' : 'До / После'}
          </button>

          {/* Скачать ▾ */}
          <div className="relative">
            <button
              ref={downloadBtnRef}
              className="btn-secondary text-xs py-1 px-2 flex items-center gap-1"
              onClick={() => {
                const rect = downloadBtnRef.current?.getBoundingClientRect();
                setDropdownRect(rect ?? null);
                setOpenDropdown((v) => v === 'download' ? null : 'download');
              }}
            >
              Скачать
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M2 3.5l3 3 3-3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </button>
            {openDropdown === 'download' && dropdownRect && (
              <div
                style={{ position: 'fixed', top: dropdownRect.bottom + 4, right: window.innerWidth - dropdownRect.right }}
                className="z-[9999] bg-white dark:bg-[#242424] border border-gray-200 dark:border-[#3a3a3a] rounded-xl shadow-panel py-1 min-w-[170px]"
                onMouseLeave={() => setOpenDropdown(null)}
              >
                <button className="w-full text-left text-xs px-3 py-2 hover:bg-gray-50"
                        onClick={() => { onDownload(doc, 'processed'); setOpenDropdown(null); }}>Исправленный .docx</button>
                {doc.status === 'done' && (
                  <button className="w-full text-left text-xs px-3 py-2 hover:bg-gray-50"
                          onClick={() => { onDownload(doc, 'processed_pdf'); setOpenDropdown(null); }}>Исправленный .pdf</button>
                )}
              </div>
            )}
          </div>

          <button className="btn-secondary text-xs py-1 px-2"
                  onClick={() => onDownload(doc, 'report_pdf')}>
            Отчёт .pdf
          </button>

          <button className="btn-secondary text-xs py-1 px-2" onClick={() => setShowHistory(true)}>↺ История</button>
        </div>
      </div>

      {/* Мобильные вкладки */}
      <div className="md:hidden shrink-0 flex border-b bg-white dark:bg-[#1e1e1e] dark:border-[#3a3a3a]">
        <button
          className={`flex-1 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
            activeMobileTab === 'violations'
              ? 'border-brand-600 text-brand-600'
              : 'border-transparent text-gray-500'
          }`}
          onClick={() => setActiveMobileTab('violations')}
        >
          Замечания
        </button>
        <button
          className={`flex-1 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
            activeMobileTab === 'pdf'
              ? 'border-brand-600 text-brand-600'
              : 'border-transparent text-gray-500'
          }`}
          onClick={() => setActiveMobileTab('pdf')}
        >
          Документ
        </button>
      </div>

      {/* Тело */}
      <div className="flex flex-1 overflow-hidden">

        {/* Панель превью DOCX — в режиме До/После делим пополам */}
        <div className={`flex-1 overflow-hidden flex ${activeMobileTab !== 'pdf' ? 'hidden md:flex' : 'flex'}`}>
          {showSplit && (
            <div className="flex-1 overflow-hidden border-r">
              <PdfPane url={originalPdfUrl} label="Оригинал (до)" />
            </div>
          )}
          <div className="flex-1 overflow-hidden">
            <PdfPane
              url={pdfUrl}
              label={showSplit ? 'Исправленный (после)' : 'Исправленный документ'}
              highlights={allHighlightTexts}
              activeText={postFixScrollText || activeText}
              refreshing={previewRefreshing}
              onHighlightClick={(needle) => {
                const hit = violations.find((v) => violationNeedle(v) === needle);
                if (hit) handleViolationClick(hit);
              }}
            />
          </div>
        </div>

        {/* Draggable-разделитель */}
        <div
          ref={dragRef}
          className="hidden md:flex shrink-0 w-1.5 cursor-col-resize items-center justify-center bg-transparent hover:bg-brand-100 active:bg-brand-200 transition-colors group z-10"
          onMouseDown={onDividerMouseDown}
        >
          <div className="w-0.5 h-8 rounded-full bg-gray-300 group-hover:bg-brand-400 transition-colors" />
        </div>

        {/* Правая панель */}
        <div
          className={`shrink-0 flex flex-col overflow-hidden bg-white dark:bg-[#252525] w-full ${activeMobileTab !== 'violations' ? 'hidden md:flex' : 'flex'}`}
          style={{ width: panelWidth }}
        >

          {/* История изменений (drawer) */}
          {showHistory && (
            <SnapshotHistory
              documentId={doc.id}
              onRollback={() => { onRollback(); setPdfVersion((n) => n + 1); setShowHistory(false); }}
              onClose={() => setShowHistory(false)}
            />
          )}

          {/* Действия в правой панели */}
          <div className="shrink-0 px-4 pt-3 pb-2 border-b space-y-2">
            {violations.some((v) => v.type === 'heading_number_conflict' && v.status === 'manual_required') && (
              <button className="btn-primary text-xs py-1 px-2 w-full" onClick={onOpenConflictReview}>
                Разрешить конфликты нумерации (PDF-режим)
              </button>
            )}

            {/* S-18: блок «Сдача руководителю» */}
            <div className="pt-2 border-t border-gray-100 space-y-2">
              {!doc.approval_status && doc.status === 'done' && (
                <>
                  <button
                    className="btn-primary text-xs py-1 px-2 w-full disabled:opacity-50 disabled:cursor-not-allowed"
                    onClick={onSubmitForReview}
                    disabled={!hasSupervisor}
                    title={!hasSupervisor ? 'Сначала выберите научного руководителя в настройках' : undefined}
                  >
                    Отправить руководителю на проверку
                  </button>
                  {!hasSupervisor && (
                    <p className="text-xs text-red-700 bg-red-50 rounded px-2 py-1.5 text-center">
                      Сначала выберите научного руководителя в настройках
                    </p>
                  )}
                </>
              )}
              {doc.approval_status === 'pending_review' && (
                <p className="text-xs text-amber-700 bg-amber-50 rounded px-2 py-1.5 text-center">
                  Документ отправлен руководителю — ожидает проверки
                </p>
              )}
              {doc.approval_status === 'approved' && (
                <div className="text-xs text-emerald-800 bg-emerald-50 rounded px-2 py-1.5">
                  <p className="font-medium">✓ Принят руководителем</p>
                  {doc.approval_comment && (
                    <p className="mt-1 text-emerald-700 whitespace-pre-wrap">«{doc.approval_comment}»</p>
                  )}
                </div>
              )}
              {doc.approval_status === 'rejected' && (
                <div className="text-xs text-red-800 bg-red-50 rounded px-2 py-1.5 space-y-1">
                  <p className="font-medium">Отклонён руководителем</p>
                  {doc.approval_comment && (
                    <p className="text-red-700 whitespace-pre-wrap">«{doc.approval_comment}»</p>
                  )}
                  <button
                    className="btn-primary text-xs py-1 px-2 w-full mt-1"
                    onClick={onSubmitForReview}
                  >
                    Отправить повторно
                  </button>
                </div>
              )}

              {/* История раундов */}
              {reviewHistory.length > 0 && (
                <details className="text-xs">
                  <summary className="cursor-pointer text-slate-400 hover:text-slate-600 select-none">
                    История проверок ({reviewHistory.length})
                  </summary>
                  <ol className="mt-1.5 space-y-1.5 pl-1">
                    {reviewHistory.map((r, i) => (
                      <li key={r.id} className="space-y-0.5">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="text-slate-400">#{i + 1}</span>
                          <span className={`badge text-[10px] ${APPROVAL_BADGE_STUDENT[r.decision] ?? 'bg-gray-100 text-gray-600'}`}>
                            {APPROVAL_LABELS_STUDENT[r.decision] ?? r.decision}
                          </span>
                          <span className="text-slate-400">{r.decided_by_name}</span>
                        </div>
                        {r.comment && (
                          <p className="text-slate-600 whitespace-pre-wrap pl-4">«{r.comment}»</p>
                        )}
                      </li>
                    ))}
                  </ol>
                </details>
              )}

              {/* Переписка с руководителем */}
              <div>
                <button
                  type="button"
                  className="btn-secondary text-xs py-1.5 px-3 w-full flex items-center justify-between gap-2"
                  onClick={() => {
                    setShowChat((v) => {
                      if (!v) markSeen(doc.id);
                      return !v;
                    });
                  }}
                >
                  <span className="flex items-center gap-1.5">
                    <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
                      <path d="M1 1h11v8H7.5L4 12V9H1V1z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/>
                    </svg>
                    {showChat
                      ? 'Скрыть переписку'
                      : `Переписка с руководителем${comments.length ? ` (${comments.length})` : ''}`}
                  </span>
                  {!showChat && hasUnread(doc) && (
                    <span className="w-2 h-2 rounded-full bg-danger-500 shrink-0" />
                  )}
                </button>
                {showChat && (
                  <div className="mt-2 border border-slate-200 rounded-xl overflow-hidden">
                    <div className="max-h-48 overflow-auto p-2 space-y-1.5 bg-slate-50">
                      {comments.length === 0 && (
                        <p className="text-xs text-slate-400 text-center py-2">Сообщений пока нет.</p>
                      )}
                      {comments.map((c) => {
                        const isMine = c.author_id === currentUser?.id;
                        return (
                          <div key={c.id} className={`flex flex-col ${isMine ? 'items-end' : 'items-start'}`}>
                            <div className={`max-w-[85%] rounded-2xl px-2.5 py-1.5 text-xs ${
                              isMine
                                ? 'bg-brand-600 text-white rounded-br-none'
                                : 'bg-white text-slate-800 border border-slate-200 rounded-bl-none'
                            }`}>
                              <p className="whitespace-pre-wrap break-words">{c.body}</p>
                            </div>
                            <p className="text-[10px] text-slate-400 mt-0.5 px-1">
                              {ROLE_LABELS_STUDENT[c.author_role] ?? c.author_role} · {new Date(c.created_at).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })}
                            </p>
                          </div>
                        );
                      })}
                      <div ref={chatBottomRef} />
                    </div>
                    <div className="p-2 border-t border-slate-200 bg-white flex gap-1.5">
                      <input
                        type="text"
                        className="input flex-1 text-xs py-1"
                        placeholder="Написать…"
                        value={chatText}
                        onChange={(e) => setChatText(e.target.value)}
                        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); sendChat(); } }}
                        disabled={chatBusy}
                      />
                      <button
                        type="button"
                        className="btn-primary text-xs px-2 py-1 disabled:opacity-50"
                        onClick={sendChat}
                        disabled={chatBusy || !chatText.trim()}
                      >
                        →
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Список нарушений */}
          <div className="shrink-0 px-4 pt-3 pb-1 flex items-center gap-2">
            <h2 className="font-semibold text-gray-900 text-sm">Замечания</h2>
            {unresolvedCount > 0 && (
              <span className="text-gray-400 text-xs">({unresolvedCount} требует внимания)</span>
            )}
            {unresolvedCount === 0 && violations.length > 0 && (
              <span className="text-emerald-600 text-xs">Все исправлены</span>
            )}
            <span className="ml-auto"><NormativeDocsButton /></span>
          </div>
          <div className="shrink-0 flex gap-1.5 px-4 pb-2">
            <select
              value={filterSeverity}
              onChange={(e) => setFilterSeverity(e.target.value)}
              className="input py-0.5 px-1.5 text-[11px] flex-1"
            >
              <option value="all">Все типы</option>
              <option value="critical">Критические</option>
              <option value="warning">Предупреждения</option>
              <option value="info">Инфо</option>
            </select>
            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              className="input py-0.5 px-1.5 text-[11px] flex-1"
            >
              <option value="manual_required">Вручную</option>
              <option value="auto_fixed">Авто</option>
              <option value="all">Все</option>
            </select>
          </div>
          <div className="flex-1 overflow-auto px-4 pb-4 space-y-2">
            {groupedViolations.length === 0 && (
              <p className="text-sm text-gray-400">
                {violations.length === 0
                  ? 'Замечания не найдены или ещё не рассчитаны.'
                  : filterSeverity !== 'all' || filterStatus !== 'manual_required'
                    ? 'Нет замечаний по выбранным фильтрам.'
                    : 'Все замечания исправлены.'}
              </p>
            )}
            {groupedViolations.map((item) => {
              const renderCard = (v) => (
                <div
                  key={v.id}
                  ref={(el) => { violationRefs.current[v.id] = el; }}
                  onClick={() => handleViolationClick(v)}
                  className={`rounded-xl border p-3 space-y-1.5 cursor-pointer transition-colors ${
                    v.id === activeId ? 'border-blue-400 bg-blue-50' : 'border-gray-100 hover:border-gray-200 hover:bg-gray-50'
                  }`}
                >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-1.5 flex-wrap min-w-0">
                    <span className={`badge text-xs ${SEVERITY_BADGE[v.severity] ?? 'bg-gray-100 text-gray-600'}`}>
                      {SEVERITY_RU[v.severity] ?? 'Замечание'}
                    </span>
                    <p className="font-medium text-gray-900 text-xs">{violationTypeLabel(v.type)}</p>
                  </div>
                  <span className="badge bg-gray-100 text-gray-600 text-xs shrink-0">{VIOLATION_STATUS_RU[v.status] ?? 'Требует проверки'}</span>
                </div>
                <p className="text-xs text-gray-400">
                  Правило:{' '}
                  <a
                    href="/api/v1/normative/reference-docs/prikaz-697-1"
                    target="_blank"
                    rel="noreferrer"
                    className="text-blue-400 hover:text-blue-600"
                    title="Открыть Приказ №697-01"
                  >
                    {v.rule_reference}
                  </a>
                </p>
                <p className="text-xs text-gray-700">{v.description}</p>
                {v.original_text && <p className="text-xs text-gray-500">Было: <span className="font-mono">{v.original_text}</span></p>}
                {v.fixed_text    && <p className="text-xs text-emerald-700">Стало: <span className="font-mono">{v.fixed_text}</span></p>}
                {v.supervisor_comment && (
                  <p className="text-xs text-indigo-700 bg-indigo-50 rounded px-2 py-1 whitespace-pre-wrap">
                    Комментарий руководителя: «{v.supervisor_comment}»
                  </p>
                )}
                {v.detector_signals && v.detector_signals.length > 0 && (
                  <details
                    className="text-xs"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <summary className="cursor-pointer text-gray-400 hover:text-gray-600 select-none">
                      Почему сервис посчитал это возможным заголовком ({v.detector_signals.length})
                    </summary>
                    <p className="mt-1 ml-4 text-[11px] text-gray-400 leading-snug">
                      Признаки — по исходному файлу. В исправленном документе
                      оформление приведено к ГОСТ (полужирный и центрирование
                      сняты), поэтому на превью их не видно.
                    </p>
                    <ul className="mt-1 ml-4 list-disc text-gray-500 space-y-0.5">
                      {v.detector_signals.map((s, i) => (
                        <li key={i}>{humaniseSignal(s)}</li>
                      ))}
                    </ul>
                  </details>
                )}

                {v.type === 'heading_number_conflict' && v.status === 'manual_required' && v.fix_options?.length > 0 && (
                  <div className="pt-1.5 space-y-1.5" onClick={(e) => e.stopPropagation()}>
                    <div className="flex flex-wrap gap-3">
                      {v.fix_options.map((opt, idx) => (
                        <label key={opt} className="flex items-center gap-1 cursor-pointer text-xs">
                          <input
                            type="radio"
                            name={`fix-${v.id}`}
                            value={opt}
                            checked={(chosenNumbers[v.id] ?? v.fix_options[1] ?? v.fix_options[0]) === opt}
                            onChange={() => setChosenNumbers((p) => ({ ...p, [v.id]: opt }))}
                            className="accent-blue-600"
                          />
                          <span className="font-mono font-semibold">{opt}.</span>
                          <span className="text-gray-400">{['(оставить)', '(рекоменд.)', '(альтернатива)'][idx] ?? ''}</span>
                        </label>
                      ))}
                      <label className="flex items-center gap-1 cursor-pointer text-xs">
                        <input
                          type="radio"
                          name={`fix-${v.id}`}
                          value={CUSTOM}
                          checked={(chosenNumbers[v.id] ?? v.fix_options[1] ?? v.fix_options[0]) === CUSTOM}
                          onChange={() => setChosenNumbers((p) => ({ ...p, [v.id]: CUSTOM }))}
                          className="accent-blue-600"
                        />
                        <span className="text-gray-600">Свой:</span>
                        <input
                          type="text"
                          inputMode="decimal"
                          placeholder="1.2.3"
                          value={customInlineNumbers[v.id] ?? ''}
                          onClick={() => setChosenNumbers((p) => ({ ...p, [v.id]: CUSTOM }))}
                          onChange={(e) => {
                            setCustomInlineNumbers((p) => ({ ...p, [v.id]: e.target.value }));
                            setChosenNumbers((p) => ({ ...p, [v.id]: CUSTOM }));
                          }}
                          className="input py-0 px-1.5 text-xs font-mono w-20"
                        />
                      </label>
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <button
                        className="btn-primary py-0.5 px-2 text-xs disabled:opacity-50 disabled:cursor-not-allowed"
                        disabled={applyingId !== null}
                        onClick={() => {
                          const chosen = chosenNumbers[v.id] ?? v.fix_options[1] ?? v.fix_options[0];
                          if (chosen === CUSTOM) {
                            const raw = (customInlineNumbers[v.id] || '').trim();
                            if (!/^\d+(\.\d+){0,2}$/.test(raw)) {
                              alert('Номер должен быть в формате 1, 1.2 или 1.2.3');
                              return;
                            }
                            handleFixAndBustPreview(v.id, raw);
                          } else {
                            handleFixAndBustPreview(v.id, chosen);
                          }
                        }}
                      >
                        {applyingId === v.id ? 'Применяю…' : 'Применить как заголовок'}
                      </button>
                      <span className="text-[11px] text-gray-400">или это:</span>
                      <button
                        className="btn-secondary py-0.5 px-2 text-[11px] disabled:opacity-50 disabled:cursor-not-allowed"
                        disabled={applyingId !== null}
                        title="Понизить до обычного абзаца тела документа"
                        onClick={() => handleDemoteAndBustPreview(v.id, 'text')}
                      >
                        {applyingId === v.id ? '…' : 'обычный текст'}
                      </button>
                      <button
                        className="btn-secondary py-0.5 px-2 text-[11px] disabled:opacity-50 disabled:cursor-not-allowed"
                        disabled={applyingId !== null}
                        title="Считать строкой нумерованного списка (тоже body-стиль, отличие в audit)"
                        onClick={() => handleDemoteAndBustPreview(v.id, 'list')}
                      >
                        {applyingId === v.id ? '…' : 'пункт списка'}
                      </button>
                    </div>
                  </div>
                )}
                {v.type === 'caption_renumbered' && v.status === 'manual_required' && (
                  <div className="space-y-1 pt-1" onClick={(e) => e.stopPropagation()}>
                  {violationNeedle(v) && (
                    <button
                      type="button"
                      className="text-[11px] text-blue-600 hover:text-blue-800 hover:underline flex items-center gap-1"
                      title="Подсветить эту подпись в PDF и пролистать к ней"
                      onClick={() => handleViolationClick(v)}
                    >
                      <span aria-hidden>↳</span> Перейти к месту в документе
                    </button>
                  )}
                  <div className="flex gap-1.5">
                    <button
                      className="btn-primary py-1 px-2 text-xs flex-1 disabled:opacity-50 disabled:cursor-not-allowed"
                      disabled={applyingId !== null}
                      onClick={() => onApplyAction(v.id, 'accept')}
                    >Принять</button>
                    <button
                      className="btn-danger py-1 px-2 text-xs flex-1 disabled:opacity-50 disabled:cursor-not-allowed"
                      disabled={applyingId !== null}
                      onClick={() => handleRevertCaptionAndBustPreview(v.id)}
                    >{applyingId === v.id ? '…' : 'Отменить исправление'}</button>
                  </div>
                  </div>
                )}
                {v.status === 'auto_fixed' && (
                  <div className="pt-1" onClick={(e) => e.stopPropagation()}>
                    <button
                      className="btn-danger py-1 px-2 text-xs w-full disabled:opacity-50 disabled:cursor-not-allowed"
                      disabled={applyingId !== null}
                      title="Отменить автоматическое исправление — вернуть как было в загруженном файле"
                      onClick={() => handleRevertAutoFixAndBustPreview(v.id)}
                    >{applyingId === v.id ? '…' : 'Отменить'}</button>
                  </div>
                )}
                {v.type !== 'heading_number_conflict' && v.type !== 'caption_renumbered' && v.status === 'manual_required' && (
                  <div className="space-y-2 pt-1" onClick={(e) => e.stopPropagation()}>
                    {(v.type === 'possible_missed_heading' || v.type === 'heading_confirm') && (
                      <div className="space-y-1 rounded-lg bg-blue-50/60 p-2 border border-blue-100">
                        <p className="text-[11px] text-gray-700 leading-snug">
                          Сейчас этот абзац — <span className="font-medium">обычный текст</span>. Если это раздел — оформить как заголовок: укажите номер (например, <span className="font-mono">2.1.3</span>) или оставьте пустым для разделов без номера (Введение/Заключение).
                        </p>
                        <div className="flex gap-1.5 items-center">
                          <input
                            type="text"
                            inputMode="decimal"
                            placeholder="2.1.3"
                            value={promoteNumbers[v.id] ?? ''}
                            onChange={(e) => setPromoteNumbers((p) => ({ ...p, [v.id]: e.target.value }))}
                            className="input py-0.5 px-2 text-xs font-mono w-24"
                          />
                          <button
                            className="btn-primary py-0.5 px-2 text-xs"
                            onClick={() => handlePromoteAndBustPreview(v.id)}
                            title="Применить heading-стиль к этому абзацу с указанным номером"
                          >Применить</button>
                        </div>
                        <button
                          className="btn-secondary py-0.5 px-2 text-[11px] w-full disabled:opacity-50 disabled:cursor-not-allowed"
                          disabled={applyingId !== null}
                          title="Это не заголовок — оставить обычным текстом (это уже так, документ не меняется)"
                          onClick={() => handleDemoteAndBustPreview(v.id, 'text', { skipPreview: true })}
                        >{applyingId === v.id ? '…' : 'Это не заголовок (оставить как есть)'}</button>
                      </div>
                    )}
                    <button
                      title="Скрыть замечание из активных — вы ознакомились с ним и решите сами"
                      className="btn-secondary py-1 px-2 text-xs w-full"
                      onClick={() => onApplyAction(v.id, 'accept')}
                    >Ознакомлен</button>
                  </div>
                )}
              </div>
            );   // конец renderCard

            if (item.kind === 'single') return renderCard(item.v);

            // hn_group: корневое нарушение + свёрнутые cascade-дочерние
            const { root, children } = item;
            const isExpanded = expandedCascade.has(root.id);
            return (
              <div key={root.id} className="space-y-1">
                {renderCard(root)}
                {children.length > 0 && (
                  <div className="pl-3 border-l-2 border-amber-200">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setExpandedCascade((prev) => {
                          const n = new Set(prev);
                          if (n.has(root.id)) n.delete(root.id); else n.add(root.id);
                          return n;
                        });
                      }}
                      className="text-xs text-amber-700 hover:text-amber-900 py-1"
                    >
                      {isExpanded ? '▾' : '▸'} Зависимые нарушения нумерации ({children.length})
                      {!isExpanded && (
                        <span className="text-gray-400 ml-1"> — часто исправляются после правки выше</span>
                      )}
                    </button>
                    {isExpanded && (
                      <div className="space-y-1 pt-1 pb-2">
                        {children.map((child) => renderCard(child))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Настройки ─────────────────────────────────────────────────────────────────

function SettingsView({ currentUser, onUserUpdate, toast }) {
  const [curPwd, setCurPwd]   = useState('');
  const [newPwd, setNewPwd]   = useState('');
  const [newPwd2, setNewPwd2] = useState('');
  const [savingPwd, setSavingPwd] = useState(false);

  const changePassword = async () => {
    if (newPwd !== newPwd2) { toast('Пароли не совпадают'); return; }
    if (newPwd.length < 8)  { toast('Пароль должен быть не менее 8 символов'); return; }
    setSavingPwd(true);
    try {
      await api.patch('/auth/me', { current_password: curPwd, new_password: newPwd });
      setCurPwd(''); setNewPwd(''); setNewPwd2('');
      toast('Пароль изменён');
    } catch (e) {
      toast(getApiErrorMessage(e, 'Ошибка смены пароля'));
    } finally {
      setSavingPwd(false);
    }
  };

  return (
    <div className="p-4 md:p-8 space-y-6 overflow-auto h-full max-w-lg">
      <h1 className="text-2xl font-semibold text-gray-900">Настройки</h1>

      {/* Профиль */}
      <div className="card p-6 space-y-3">
        <h2 className="font-semibold text-gray-900">Профиль</h2>
        <div>
          <p className="text-xs text-gray-400 mb-0.5">ФИО</p>
          <p className="text-sm text-gray-700">{currentUser?.full_name ?? '—'}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400 mb-0.5">Email</p>
          <p className="text-sm text-gray-700">{currentUser?.email ?? '—'}</p>
        </div>
      </div>

      {/* Научный руководитель — только просмотр, назначается руководителем */}
      <div className="card p-6 space-y-2">
        <h2 className="font-semibold text-gray-900">Научный руководитель</h2>
        {currentUser?.supervisor_name
          ? <p className="text-sm text-gray-700">{currentUser.supervisor_name}</p>
          : <p className="text-sm text-gray-400">Не назначен. Обратитесь к научному руководителю — он прикрепит вас в системе.</p>
        }
      </div>

      {/* Смена пароля */}
      <div className="card p-6 space-y-3">
        <h2 className="font-semibold text-gray-900">Смена пароля</h2>
        <input
          className="input"
          type="password"
          placeholder="Текущий пароль"
          value={curPwd}
          onChange={(e) => setCurPwd(e.target.value)}
        />
        <input
          className="input"
          type="password"
          placeholder="Новый пароль (не менее 8 символов)"
          value={newPwd}
          onChange={(e) => setNewPwd(e.target.value)}
        />
        <input
          className="input"
          type="password"
          placeholder="Повторите новый пароль"
          value={newPwd2}
          onChange={(e) => setNewPwd2(e.target.value)}
        />
        <button
          className="btn-primary py-1.5 px-4 text-sm disabled:opacity-50"
          disabled={savingPwd || !curPwd || !newPwd}
          onClick={changePassword}
        >
          {savingPwd ? 'Сохраняю…' : 'Изменить пароль'}
        </button>
      </div>
    </div>
  );
}

// ── Корневой компонент ────────────────────────────────────────────────────────

function StudentPage() {
  const [activeView,        setActiveView]        = useState('documents');
  const [documents,         setDocuments]         = useState([]);
  const [processingDocId,   setProcessingDocId]   = useState(null);
  const [selectedDoc,       setSelectedDoc]       = useState(null);
  const [violations,        setViolations]        = useState([]);
  const [conflictReviewDoc, setConflictReviewDoc] = useState(null);
  const [toastMsg,          setToastMsg]          = useState('');
  const [currentUser,       setCurrentUser]       = useState(null);

  useEffect(() => {
    api.get('/auth/me').then((r) => setCurrentUser(r.data)).catch(() => {});
  }, []);

  const toast = (msg) => { setToastMsg(msg); setTimeout(() => setToastMsg(''), 4000); };

  const refreshDocuments = useCallback(async () => {
    try {
      const res = await api.get('/documents/');
      setDocuments(res.data);
    } catch (err) {
      if (err?.response?.status !== 401) {
        toast(getApiErrorMessage(err, 'Ошибка загрузки списка документов'));
      }
    }
  }, []);

  useEffect(() => {
    refreshDocuments();
    const timer = setInterval(refreshDocuments, 5000);
    return () => clearInterval(timer);
  }, [refreshDocuments]);

  // Держим выбранный/обрабатываемый документ в синке с обновлениями polling'а
  const processingDoc = useMemo(
    () => documents.find((d) => d.id === processingDocId) ?? null,
    [documents, processingDocId]
  );

  // По завершении: если обработка done/error, остаёмся на странице загрузки,
  // чтобы пользователь увидел результат (уйти он может сам).

  const handleUploadFile = (formData) => api.post('/documents/upload', formData);

  const handleNavigateUpload = (docId) => {
    if (docId) setProcessingDocId(docId);
    setActiveView('upload');
  };

  const handleSelectDoc = async (doc) => {
    setSelectedDoc(doc);
    setActiveView('detail');
    try {
      const res = await api.get(`/violations/${doc.id}`);
      setViolations(res.data);
    } catch (err) {
      if (err?.response?.status !== 401) toast(getApiErrorMessage(err, 'Ошибка загрузки нарушений'));
    }
  };

  const handleDownload = async (doc, kind) => {
    const baseName = doc.original_filename ?? 'document.docx';
    const targets = {
      original:      { endpoint: `/documents/${doc.id}/download/original`,       fallback: baseName },
      processed:     { endpoint: `/documents/${doc.id}/download/processed`,       fallback: `processed_${baseName.replace(/\.[^/.]+$/, '')}.docx` },
      processed_pdf: { endpoint: `/documents/${doc.id}/download/processed-pdf`,  fallback: `processed_${baseName.replace(/\.[^/.]+$/, '')}.pdf` },
      report_pdf:    { endpoint: `/documents/${doc.id}/report`,  fallback: `report_${doc.id}.pdf` }
    };
    const target = targets[kind];
    if (!target) return;
    try {
      const res = await api.get(target.endpoint, { responseType: 'blob' });
      if (kind === 'report_pdf') {
        const blobUrl = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
        const win = window.open(blobUrl, '_blank');
        if (win) win.addEventListener('load', () => URL.revokeObjectURL(blobUrl), { once: true });
        else setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
      } else {
        const name = parseFileNameFromHeaders(res.headers, target.fallback);
        triggerDownload(res.data, name);
      }
    } catch (err) {
      toast(getApiErrorMessage(err, 'Ошибка скачивания файла'));
    }
  };

  const handleApplyAction = async (id, action) => {
    // Оптимистично гасим карточку сразу — подчёркивание в превью исчезает
    // мгновенно (allHighlightTexts фильтрует по status==='manual_required'),
    // не дожидаясь сетевого round-trip. Затем сверяемся с сервером.
    const optimistic = action === 'reject' ? 'rejected' : 'accepted';
    setViolations((prev) =>
      prev.map((v) => (v.id === id ? { ...v, status: optimistic } : v)),
    );
    try {
      await api.patch(`/violations/${id}/${action}`);
    } finally {
      if (selectedDoc) {
        const res = await api.get(`/violations/${selectedDoc.id}`);
        setViolations(res.data);
      }
    }
  };

  const handleFixHeadingNumber = async (violationId, chosenNumber) => {
    try {
      await api.patch(`/violations/${violationId}/fix-heading-number`, { chosen_number: chosenNumber });
      if (selectedDoc) {
        const res = await api.get(`/violations/${selectedDoc.id}`);
        setViolations(res.data);
      }
    } catch (err) {
      toast(getApiErrorMessage(err, 'Не удалось применить исправление'));
      throw err;
    }
  };

  const handleDemoteHeading = async (violationId, asKind) => {
    setViolations((prev) =>
      prev.map((v) => (v.id === violationId ? { ...v, status: 'accepted' } : v)),
    );
    try {
      await api.patch(`/violations/${violationId}/demote-heading-to-text`, { as_kind: asKind });
      if (selectedDoc) {
        const res = await api.get(`/violations/${selectedDoc.id}`);
        setViolations(res.data);
      }
    } catch (err) {
      toast(getApiErrorMessage(err, 'Не удалось понизить заголовок до обычного текста'));
      if (selectedDoc) {
        const res = await api.get(`/violations/${selectedDoc.id}`);
        setViolations(res.data); // откат оптимистичного статуса
      }
      throw err;
    }
  };

  const handleRevertCaption = async (violationId) => {
    try {
      await api.patch(`/violations/${violationId}/revert-caption`);
      if (selectedDoc) {
        const res = await api.get(`/violations/${selectedDoc.id}`);
        setViolations(res.data);
      }
    } catch (err) {
      toast(getApiErrorMessage(err, 'Не удалось отменить исправление'));
      throw err;
    }
  };

  const handleRevertAutoFix = async (violationId) => {
    try {
      await api.patch(`/violations/${violationId}/revert`);
      if (selectedDoc) {
        const res = await api.get(`/violations/${selectedDoc.id}`);
        setViolations(res.data);
      }
    } catch (err) {
      toast(getApiErrorMessage(err, 'Не удалось откатить авто-исправление'));
      throw err;
    }
  };

  const handlePromoteToHeading = async (violationId, chosenNumber) => {
    setViolations((prev) =>
      prev.map((v) => (v.id === violationId ? { ...v, status: 'auto_fixed' } : v)),
    );
    try {
      const payload = chosenNumber ? { chosen_number: chosenNumber } : {};
      await api.patch(`/violations/${violationId}/promote-to-heading`, payload);
      if (selectedDoc) {
        const res = await api.get(`/violations/${selectedDoc.id}`);
        setViolations(res.data);
      }
    } catch (err) {
      toast(getApiErrorMessage(err, 'Не удалось оформить заголовок'));
      if (selectedDoc) {
        const res = await api.get(`/violations/${selectedDoc.id}`);
        setViolations(res.data); // откат оптимистичного статуса
      }
      throw err;
    }
  };

  const handleRefreshViolations = async (docId) => {
    const res = await api.get(`/violations/${docId}`);
    if (selectedDoc?.id === docId) setViolations(res.data);
    return res.data;
  };


  const handleRollback = async () => {
    if (!selectedDoc) return;
    try {
      const res = await api.get(`/violations/${selectedDoc.id}`);
      setViolations(res.data);
      toast('Изменения отменены — документ восстановлен к выбранному состоянию');
    } catch (err) {
      toast(getApiErrorMessage(err, 'Ошибка обновления после отката'));
    }
  };

  const handleOpenConflictReview = () => {
    if (selectedDoc) setConflictReviewDoc(selectedDoc);
  };

  // S-18: студент отправляет документ на проверку руководителю.
  // После успеха обновляем документ в локальном списке (статус → pending_review),
  // чтобы UI сразу отразил кнопку «На проверке» вместо «Отправить руководителю».
  const handleSubmitForReview = async () => {
    if (!selectedDoc) return;
    try {
      const res = await api.post(`/documents/${selectedDoc.id}/submit-for-review`);
      setDocuments((prev) => prev.map((d) => (d.id === selectedDoc.id ? res.data : d)));
      setSelectedDoc(res.data);
      setToastMsg('Документ отправлен руководителю на проверку');
    } catch (e) {
      setToastMsg(getApiErrorMessage(e, 'Не удалось отправить на проверку'));
    }
  };

  const handleNavChange = (view) => {
    if (view === 'upload' && !processingDocId) {
      // Активного документа нет — показываем страницу загрузки с подсказкой
    }
    setActiveView(view);
  };

  const resolvedView = activeView;

  // Непрочитанные сообщения: текущий документ студента — первый в списке.
  const currentDoc = documents[0] ?? null;
  const navItemsWithBadge = useMemo(
    () => NAV_ITEMS.map((item) =>
      item.id === 'documents' ? { ...item, badge: hasUnread(currentDoc) } : item
    ),
    [documents],  // пересчитывается при каждом poll (каждые 5 с)
  );

  return (
    <Layout navItems={navItemsWithBadge} activeView={activeView} onNavChange={handleNavChange}>
      {/* Тост-уведомление */}
      {toastMsg && (
        <div className="fixed top-4 right-4 z-50 bg-white dark:bg-[#242424] border border-gray-200 dark:border-[#3a3a3a] shadow-lg rounded-xl px-4 py-3 text-sm text-gray-800 dark:text-[#f0f0f0] max-w-sm">
          {toastMsg}
        </div>
      )}

      {resolvedView === 'documents' && (
        <DocumentsView
          documents={documents}
          currentUser={currentUser}
          onNavigateUpload={handleNavigateUpload}
          onUploadFile={handleUploadFile}
          onSelectDoc={handleSelectDoc}
          onDownload={handleDownload}
          toast={toast}
        />
      )}

      {resolvedView === 'upload' && (
        <ProcessingView
          doc={processingDoc}
          onCancel={() => {
            setProcessingDocId(null);
            setActiveView('documents');
          }}
          onNavigateDocs={() => setActiveView('documents')}
          onViewResult={() => processingDoc && handleSelectDoc(processingDoc)}
          onUploadFile={async (formData) => {
            const res = await handleUploadFile(formData);
            handleNavigateUpload(res.data.document.id);
            return res;
          }}
          toast={toast}
        />
      )}

      {resolvedView === 'detail' && selectedDoc && !conflictReviewDoc && (
        <DetailView
          doc={selectedDoc}
          violations={violations}
          currentUser={currentUser}
          onDownload={handleDownload}
          onApplyAction={handleApplyAction}
          onFixHeadingNumber={handleFixHeadingNumber}
          onDemoteHeading={handleDemoteHeading}
          onPromoteToHeading={handlePromoteToHeading}
          onRevertCaption={handleRevertCaption}
          onRevertAutoFix={handleRevertAutoFix}
          onOpenConflictReview={handleOpenConflictReview}
          onSubmitForReview={handleSubmitForReview}
          onRollback={handleRollback}
          onBack={() => setActiveView('documents')}
        />
      )}

      {conflictReviewDoc && (
        <ConflictReviewPage
          doc={conflictReviewDoc}
          violations={violations}
          onBack={() => setConflictReviewDoc(null)}
          onApplyFix={handleFixHeadingNumber}
          onDemoteHeading={handleDemoteHeading}
          onRefreshViolations={handleRefreshViolations}
        />
      )}

      {activeView === 'settings' && (
        <SettingsView currentUser={currentUser} onUserUpdate={setCurrentUser} toast={toast} />
      )}
    </Layout>
  );
}

export default StudentPage;
