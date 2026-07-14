import React, { useEffect, useMemo, useRef, useState } from 'react';
import { hasUnread, markSeen } from '../utils/unreadComments';

import api from '../api/client';
import { downloadViaApi } from '../utils/download';
import Layout from '../components/Layout';
import DashboardView from '../components/DashboardView';
import PdfPane from '../components/PdfPane';
import NormativeDocsButton from '../components/NormativeDocsButton';
import getApiErrorMessage from '../utils/errorMessage';
import { violationNeedle, ACTIVE_ONLY_ANCHOR_TYPES } from '../utils/violationAnchor';
import { sortViolations } from '../utils/violationOrder';
import { SEVERITY_RU, VIOLATION_STATUS_RU, violationTypeLabel } from '../utils/violationLabels';
import { fmtDate as fmtDateFull, fmtDateShort } from '../utils/format';
import {
  APPROVAL_BADGE,
  APPROVAL_LABELS,
  ROLE_LABELS,
  STATUS_DOT,
  STATUS_LABELS,
} from '../utils/labels';

// SEVERITY_BADGE на StaffPage отличается от StudentPage визуально
// (info — синий вместо зелёного), оставляем локально.
const SEVERITY_BADGE = {
  error:   'bg-red-100 text-red-800',
  warning: 'bg-amber-100 text-amber-800',
  info:    'bg-blue-100 text-blue-800',
};

// Подписи/бейджи статусов, ролей и approval'ов — общий utils/labels.
// SEVERITY_RU (русские названия) — из utils/violationLabels.
const formatDocDate = fmtDateFull;

const STAFF_NAV_ITEMS = [
  { id: 'dashboard', label: 'Обзор' },
  { id: 'documents', label: 'Реестр ВКР' },
  { id: 'students',  label: 'Мои студенты' },
];

// В Staff-таблицах и чате места меньше — берём короткий формат.
const fmtDate = fmtDateShort;

// ── Компонент: тред комментариев ─────────────────────────────────────────────

function CommentThread({ documentId, currentUser }) {
  const [comments, setComments] = useState([]);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const bottomRef = useRef(null);

  // load() переиспользуется после send() — там AbortController не нужен,
  // мы хотим именно дождаться актуального ответа.
  const load = async (signal) => {
    try {
      const r = await api.get(`/documents/${documentId}/comments`, signal ? { signal } : undefined);
      setComments(r.data);
    } catch (e) {
      if (e?.code === 'ERR_CANCELED' || e?.name === 'CanceledError') return;
      // прочее — игнорируем (тред не критичен)
    }
  };

  useEffect(() => {
    setComments([]);
    setText('');
    setError('');
    if (!documentId) return undefined;
    // Без AbortController при быстрой смене documentId старый запрос
    // мог дотечь и затереть свежий список комментариями чужого документа.
    const abort = new AbortController();
    load(abort.signal);
    return () => abort.abort();
  }, [documentId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [comments]);

  const send = async () => {
    const body = text.trim();
    if (!body) return;
    setBusy(true);
    setError('');
    try {
      await api.post(`/documents/${documentId}/comments`, { body });
      setText('');
      await load();
    } catch (e) {
      setError(getApiErrorMessage(e, 'Не удалось отправить'));
    } finally {
      setBusy(false);
    }
  };

  if (!documentId) {
    return <p className="text-sm text-slate-400 p-4">Выберите документ.</p>;
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-auto p-3 space-y-2">
        {comments.length === 0 && (
          <p className="text-xs text-slate-400 text-center mt-4">
            Переписки пока нет. Напишите первое сообщение.
          </p>
        )}
        {comments.map((c) => {
          const isMine = c.author_id === currentUser?.id;
          return (
            <div key={c.id} className={`flex flex-col ${isMine ? 'items-end' : 'items-start'}`}>
              <div className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${
                isMine
                  ? 'bg-brand-600 text-white rounded-br-none'
                  : 'bg-slate-100 text-slate-800 rounded-bl-none'
              }`}>
                <p className="whitespace-pre-wrap break-words">{c.body}</p>
              </div>
              <p className="text-[10px] text-slate-400 mt-0.5 px-1">
                {ROLE_LABELS[c.author_role] ?? c.author_role} · {c.author_name} · {fmtDate(c.created_at)}
              </p>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>
      <div className="shrink-0 p-3 border-t border-slate-100 space-y-1.5">
        {error && <p className="text-xs text-red-700">{error}</p>}
        <div className="flex gap-2">
          <textarea
            className="input flex-1 text-sm resize-none"
            rows={2}
            placeholder="Написать сообщение…"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
            }}
            disabled={busy}
          />
          <button
            type="button"
            className="btn-primary text-sm px-3 self-end disabled:opacity-50"
            onClick={send}
            disabled={busy || !text.trim()}
          >
            {busy ? '…' : '→'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Компонент: история раундов ───────────────────────────────────────────────

function ReviewHistory({ documentId }) {
  const [rounds, setRounds] = useState([]);

  useEffect(() => {
    setRounds([]);
    if (!documentId) return undefined;
    const abort = new AbortController();
    api.get(`/documents/${documentId}/review-history`, { signal: abort.signal })
      .then((r) => setRounds(r.data))
      .catch((e) => {
        if (e?.code === 'ERR_CANCELED' || e?.name === 'CanceledError') return;
        // прочее игнорируем — история не критична
      });
    return () => abort.abort();
  }, [documentId]);

  if (!documentId) return null;
  if (rounds.length === 0) {
    return <p className="text-xs text-slate-400">Решений ещё не принималось.</p>;
  }

  return (
    <ol className="space-y-2">
      {rounds.map((r, i) => (
        <li key={r.id} className="flex gap-2 text-xs">
          <span className="shrink-0 font-medium text-slate-400">#{i + 1}</span>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className={`badge text-[10px] ${APPROVAL_BADGE[r.decision] ?? 'bg-gray-100 text-gray-600'}`}>
                {APPROVAL_LABELS[r.decision] ?? r.decision}
              </span>
              <span className="text-slate-500">{r.decided_by_name}</span>
              <span className="text-slate-400">{fmtDate(r.decided_at)}</span>
            </div>
            {r.comment && (
              <p className="mt-0.5 text-slate-600 whitespace-pre-wrap">«{r.comment}»</p>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}

// ── Компонент: список нарушений для руководителя ─────────────────────────────

function ViolationsList({ documentId, currentUser, violations, setViolations, activeId, onSelect }) {
  const [commentEditing, setCommentEditing] = useState({});
  const [commentBusy, setCommentBusy] = useState({});
  const [filterSeverity, setFilterSeverity] = useState('all'); // all|critical|warning|info
  const [filterStatus, setFilterStatus] = useState('manual_required'); // all|manual_required|auto_fixed

  useEffect(() => {
    setCommentEditing({});
  }, [documentId]);

  const saveComment = async (violationId) => {
    const draft = commentEditing[violationId] ?? '';
    setCommentBusy((p) => ({ ...p, [violationId]: true }));
    try {
      const r = await api.patch(`/violations/${violationId}/comment`, { comment: draft });
      setViolations((prev) =>
        prev.map((v) =>
          v.id === violationId ? { ...v, supervisor_comment: r.data.supervisor_comment } : v,
        ),
      );
      setCommentEditing((p) => { const n = { ...p }; delete n[violationId]; return n; });
    } catch {
      // ignore
    } finally {
      setCommentBusy((p) => ({ ...p, [violationId]: false }));
    }
  };

  if (!documentId) return <p className="text-sm text-slate-400 p-4">Выберите документ.</p>;
  if (violations.length === 0) {
    return <p className="text-sm text-slate-400 p-4">Нарушений нет или документ ещё не обработан.</p>;
  }

  const canComment = currentUser?.role && ['supervisor', 'dean', 'admin'].includes(currentUser.role);

  const ordered = sortViolations(violations);
  const filtered = ordered.filter((v) => {
    if (filterSeverity !== 'all' && v.severity !== filterSeverity) return false;
    if (filterStatus !== 'all' && v.status !== filterStatus) return false;
    return true;
  });

  return (
    <div className="flex flex-col h-full">
      {/* Фильтры */}
      <div className="shrink-0 flex gap-1.5 px-3 py-2 border-b border-slate-100 dark:border-[#3a3a3a]">
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
      {filtered.length === 0 && (
        <p className="text-sm text-slate-400 p-4">Нет замечаний по выбранным фильтрам.</p>
      )}
      <div className="flex-1 overflow-auto px-3 py-3 space-y-2">
      {filtered.map((v) => {
        const draft = commentEditing[v.id];
        const hasDraft = draft !== undefined;
        const anchorable = Boolean(violationNeedle(v));
        const isActive = activeId === v.id;

        return (
          <div
            key={v.id}
            onClick={() => anchorable && onSelect?.(isActive ? null : v.id)}
            className={`rounded-xl border p-3 space-y-1.5 transition-colors ${
              anchorable ? 'cursor-pointer' : 'cursor-default'
            } ${
              isActive
                ? 'border-brand-400 bg-brand-50/40'
                : 'border-gray-100 hover:border-gray-200 hover:bg-gray-50'
            }`}
          >
            {/* Строка 1: северити + тип + статус */}
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-1.5 flex-wrap min-w-0">
                <span className={`badge text-xs ${SEVERITY_BADGE[v.severity] ?? 'bg-gray-100 text-gray-600'}`}>
                  {SEVERITY_RU[v.severity] ?? 'Замечание'}
                </span>
                <p className="font-medium text-gray-900 text-xs">{violationTypeLabel(v.type)}</p>
              </div>
              <span className="badge bg-gray-100 text-gray-600 text-xs shrink-0">
                {VIOLATION_STATUS_RU[v.status] ?? 'Требует проверки'}
              </span>
            </div>

            {/* Строка 2: ссылка на правило */}
            <p className="text-xs text-gray-400">
              Правило:{' '}
              <a
                href="/api/v1/normative/reference-docs/prikaz-697-1"
                target="_blank"
                rel="noreferrer"
                onClick={e => e.stopPropagation()}
                className="text-slate-500 hover:text-slate-700 underline"
                title="Открыть Приказ №697-01"
              >
                {v.rule_reference}
              </a>
            </p>

            {/* Описание и diff */}
            <p className="text-xs text-gray-700">{v.description}</p>
            {v.original_text && (
              <p className="text-xs text-gray-500">Было: <span className="font-mono">{v.original_text}</span></p>
            )}
            {v.fixed_text && (
              <p className="text-xs text-emerald-700">Стало: <span className="font-mono">{v.fixed_text}</span></p>
            )}

            {/* Комментарий руководителя */}
            {canComment && (
              <div className="pt-1 border-t border-gray-100 dark:border-[#3a3a3a] mt-1" onClick={e => e.stopPropagation()}>
                {!hasDraft ? (
                  <div className="space-y-1.5">
                    {v.supervisor_comment && (
                      <p className="text-xs text-slate-600 bg-slate-50 dark:bg-[#2a2a2a] rounded px-2 py-1.5 whitespace-pre-wrap">
                        «{v.supervisor_comment}»
                      </p>
                    )}
                    <button
                      type="button"
                      className="btn-secondary text-xs py-1 px-3 w-full"
                      onClick={() => setCommentEditing((p) => ({ ...p, [v.id]: v.supervisor_comment ?? '' }))}
                    >
                      {v.supervisor_comment ? 'Изменить комментарий' : '+ Добавить комментарий'}
                    </button>
                  </div>
                ) : (
                  <div className="space-y-1">
                    <textarea
                      className="input w-full text-xs resize-none"
                      rows={2}
                      placeholder="Комментарий для студента…"
                      value={draft}
                      onChange={(e) => setCommentEditing((p) => ({ ...p, [v.id]: e.target.value }))}
                    />
                    <div className="flex gap-1.5">
                      <button
                        type="button"
                        className="btn-primary text-xs py-0.5 px-2 disabled:opacity-50"
                        onClick={() => saveComment(v.id)}
                        disabled={commentBusy[v.id]}
                      >
                        {commentBusy[v.id] ? '…' : 'Сохранить'}
                      </button>
                      <button
                        type="button"
                        className="text-xs text-slate-400 hover:text-slate-600"
                        onClick={() => setCommentEditing((p) => { const n = { ...p }; delete n[v.id]; return n; })}
                      >
                        Отмена
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
      </div>
    </div>
  );
}

// ── Управление студентами (руководитель назначает сам) ───────────────────────

function StudentsView() {
  const [myStudents, setMyStudents]   = useState([]);
  const [allStudents, setAllStudents] = useState([]);
  const [search, setSearch]           = useState('');
  const [busy, setBusy]               = useState(false);
  const [error, setError]             = useState('');

  const load = async () => {
    try {
      const [mine, all] = await Promise.all([
        api.get('/auth/my-students'),
        api.get('/auth/students'),
      ]);
      setMyStudents(mine.data);
      setAllStudents(all.data);
    } catch { /* ignore */ }
  };

  useEffect(() => { load(); }, []);

  const myIds = new Set(myStudents.map((s) => s.id));

  const assign = async (studentId) => {
    setBusy(true); setError('');
    try {
      await api.post('/auth/my-students', { student_id: studentId });
      await load();
    } catch (e) {
      setError(getApiErrorMessage(e, 'Ошибка'));
    } finally { setBusy(false); }
  };

  const unassign = async (studentId) => {
    setBusy(true); setError('');
    try {
      await api.delete(`/auth/my-students/${studentId}`);
      await load();
    } catch (e) {
      setError(getApiErrorMessage(e, 'Ошибка'));
    } finally { setBusy(false); }
  };

  const norm = search.trim().toLowerCase();
  const filtered = allStudents.filter((s) =>
    !norm
    || s.full_name?.toLowerCase().includes(norm)
    || s.email?.toLowerCase().includes(norm)
  );

  return (
    <div className="p-4 md:p-8 space-y-6 overflow-auto h-full">
      <h1 className="text-2xl font-semibold text-gray-900">Мои студенты</h1>

      {/* Прикреплённые */}
      <div className="card p-6 space-y-3">
        <h2 className="font-semibold text-gray-900">Прикреплённые ({myStudents.length})</h2>
        {myStudents.length === 0
          ? <p className="text-sm text-gray-400">Ещё никого нет. Найдите студента ниже и прикрепите его.</p>
          : (
            <ul className="divide-y divide-gray-100">
              {myStudents.map((s) => (
                <li key={s.id} className="flex items-center justify-between py-2 gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">{s.full_name || '—'}</p>
                    <p className="text-xs text-gray-400 truncate">{s.email}</p>
                  </div>
                  <button
                    className="btn-danger text-xs py-1 px-2 shrink-0"
                    disabled={busy}
                    onClick={() => unassign(s.id)}
                  >Открепить</button>
                </li>
              ))}
            </ul>
          )
        }
      </div>

      {/* Поиск и прикрепление */}
      <div className="card p-6 space-y-3">
        <h2 className="font-semibold text-gray-900">Найти студента</h2>
        <input
          className="input w-full"
          placeholder="ФИО или email…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        {error && <p className="text-xs text-red-600">{error}</p>}
        <ul className="divide-y divide-gray-100 max-h-72 overflow-auto">
          {filtered.length === 0
            ? <li className="py-3 text-sm text-gray-400">Ничего не найдено</li>
            : filtered.map((s) => (
              <li key={s.id} className="flex items-center justify-between py-2 gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">{s.full_name || '—'}</p>
                  <p className="text-xs text-gray-400 truncate">{s.email}</p>
                </div>
                {myIds.has(s.id)
                  ? <span className="text-xs text-emerald-600 shrink-0">Прикреплён</span>
                  : (
                    <button
                      className="btn-primary text-xs py-1 px-2 shrink-0"
                      disabled={busy}
                      onClick={() => assign(s.id)}
                    >Прикрепить</button>
                  )
                }
              </li>
            ))
          }
        </ul>
      </div>
    </div>
  );
}


// ── Главный компонент StaffPage ───────────────────────────────────────────────

function StaffPage() {
  const [activeView, setActiveView] = useState('dashboard');
  const [documents, setDocuments] = useState([]);
  const [report, setReport] = useState(null);
  const [stats, setStats] = useState(null);
  const [selectedDocId, setSelectedDocId] = useState(null);
  const [decisionComment, setDecisionComment] = useState('');
  const [decisionBusy, setDecisionBusy] = useState(false);
  const [decisionError, setDecisionError] = useState('');
  const [activeTab, setActiveTab] = useState('decision'); // 'decision' | 'violations' | 'chat'
  const [currentUser, setCurrentUser] = useState(null);
  const [violations, setViolations] = useState([]);
  const [activeViolationId, setActiveViolationId] = useState(null);
  // Мобильная навигация: список ↔ детали ↔ pdf
  const [mobileShowDetail, setMobileShowDetail] = useState(false);
  const [mobilePdfVisible, setMobilePdfVisible] = useState(false);
  // Реестр ВКР: поиск/фильтр/сортировка.
  const [docQuery, setDocQuery] = useState('');
  const [docStatusFilter, setDocStatusFilter] = useState('all'); // all|pending_review|approved|rejected
  const [docSort, setDocSort] = useState('status'); // status|date|name
  // Правая панель: ширина и drag-разделитель.
  const [panelWidth, setPanelWidth] = useState(360);
  const dragRef = useRef(null);

  useEffect(() => {
    api.get('/auth/me').then((r) => setCurrentUser(r.data)).catch(() => {});
    api.get('/admin/stats').then((r) => setStats(r.data)).catch(() => {});
    refreshDocuments();
  }, []);

  const refreshDocuments = async () => {
    try {
      const r = await api.get('/documents/');
      setDocuments(r.data);
    } catch {
      // ignore
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

  const openReport = async (docId) => {
    setSelectedDocId(docId);
    setReport(null);
    setDecisionComment('');
    setDecisionError('');
    setViolations([]);
    setActiveViolationId(null);
    setMobileShowDetail(true);
    setMobilePdfVisible(false);
    try {
      const response = await api.get(`/documents/${docId}/report/meta`);
      setReport(response.data);
    } catch {
      // отчёт может ещё не быть сгенерирован — это норма
    }
    try {
      const vr = await api.get(`/violations/${docId}`);
      setViolations(vr.data);
    } catch {
      // нарушений может ещё не быть — документ не обработан
    }
  };

  const decide = async (action) => {
    if (!selectedDocId) return;
    if (action === 'reject' && !decisionComment.trim()) {
      setDecisionError('Укажите причину отклонения');
      return;
    }
    setDecisionBusy(true);
    setDecisionError('');
    try {
      await api.post(`/documents/${selectedDocId}/${action}`, {
        comment: decisionComment.trim() || null,
      });
      setDecisionComment('');
      await refreshDocuments();
    } catch (e) {
      setDecisionError(getApiErrorMessage(e, 'Не удалось сохранить решение'));
    } finally {
      setDecisionBusy(false);
    }
  };

  const visibleDocuments = useMemo(() => {
    const q = docQuery.trim().toLowerCase();
    let list = documents.filter((d) => {
      if (docStatusFilter !== 'all' && (d.approval_status ?? '') !== docStatusFilter) {
        return false;
      }
      if (!q) return true;
      return (
        (d.original_filename || '').toLowerCase().includes(q) ||
        (d.owner_full_name || '').toLowerCase().includes(q)
      );
    });
    const ts = (d) => (d.uploaded_at ? new Date(d.uploaded_at).getTime() : 0);
    list = [...list];
    if (docSort === 'date') {
      list.sort((a, b) => ts(b) - ts(a));
    } else if (docSort === 'name') {
      list.sort((a, b) =>
        (a.original_filename || '').localeCompare(b.original_filename || '', 'ru'),
      );
    } else {
      // 'status' — на проверке вверху, внутри группы новее выше.
      const rank = (d) => (d.approval_status === 'pending_review' ? 0 : 1);
      list.sort((a, b) => rank(a) - rank(b) || ts(b) - ts(a));
    }
    return list;
  }, [documents, docQuery, docStatusFilter, docSort]);

  const selectedDoc = documents.find((d) => d.id === selectedDocId) ?? null;
  const previewUrl = selectedDoc && selectedDoc.status === 'done'
    ? `/api/v1/documents/${selectedDoc.id}/preview/processed`
    : null;

  const canDecide = selectedDoc && selectedDoc.approval_status === 'pending_review';

  const violationHighlights = useMemo(
    // Ссылки «[N]» (ACTIVE_ONLY) подсвечиваются только при выборе их
    // карточки (через activeViolationText), в постоянный список не идут.
    () => violations
      .filter((v) => !ACTIVE_ONLY_ANCHOR_TYPES.has(v.type))
      .map(violationNeedle)
      .filter(Boolean),
    [violations],
  );
  const activeViolationText = violationNeedle(
    violations.find((v) => v.id === activeViolationId),
  );

  const selectViolation = (id) => {
    setActiveViolationId(id);
    if (id != null) setActiveTab('violations');
  };

  const TABS = [
    { id: 'decision',   label: 'Решение' },
    { id: 'violations', label: 'Замечания' },
    { id: 'chat',       label: 'Переписка', badge: hasUnread(selectedDoc) },
  ];

  return (
    <Layout navItems={STAFF_NAV_ITEMS} activeView={activeView} onNavChange={setActiveView}>
      {activeView === 'dashboard' && (
        <DashboardView stats={stats} showStudents onUsersClick={() => setActiveView('students')} />
      )}

      {activeView === 'students' && <StudentsView />}

      {activeView === 'documents' && (
        <div className="flex flex-col h-full overflow-hidden">
          <div className="shrink-0 px-4 md:px-8 pt-4 md:pt-6 pb-3 flex items-center gap-3">
            {mobileShowDetail && (
              <button
                className="md:hidden text-sm text-gray-500 hover:text-gray-700 shrink-0"
                onClick={() => { setMobileShowDetail(false); setMobilePdfVisible(false); }}
              >
                ← Список
              </button>
            )}
            <h1 className="text-xl md:text-2xl font-semibold text-gray-900">Реестр ВКР</h1>
          </div>

          {/* ── Мобильный список ── */}
          <div className={`md:hidden flex-1 overflow-auto px-4 pb-4 space-y-2 ${mobileShowDetail ? 'hidden' : 'block'}`}>
            <div className="space-y-1.5 mb-2">
              <input
                type="text"
                value={docQuery}
                onChange={(e) => setDocQuery(e.target.value)}
                placeholder="Поиск: файл или студент"
                className="input py-1 px-2 text-xs w-full"
              />
              <div className="flex gap-1.5">
                <select
                  value={docStatusFilter}
                  onChange={(e) => setDocStatusFilter(e.target.value)}
                  className="input py-1 px-1.5 text-xs flex-1"
                >
                  <option value="all">Все статусы</option>
                  <option value="pending_review">На проверке</option>
                  <option value="approved">Принят</option>
                  <option value="rejected">Отклонён</option>
                </select>
                <select
                  value={docSort}
                  onChange={(e) => setDocSort(e.target.value)}
                  className="input py-1 px-1.5 text-xs flex-1"
                >
                  <option value="status">По статусу</option>
                  <option value="date">По дате</option>
                  <option value="name">По имени</option>
                </select>
              </div>
            </div>
            {visibleDocuments.length === 0 && (
              <p className="text-sm text-slate-500">
                {documents.length === 0 ? 'Загруженных работ ещё нет.' : 'Ничего не найдено.'}
              </p>
            )}
            {visibleDocuments.map((doc) => (
              <button
                key={doc.id}
                onClick={() => openReport(doc.id)}
                className={`w-full rounded-xl border p-3 text-left transition-colors ${
                  selectedDocId === doc.id
                    ? 'border-brand-700 bg-brand-50/40'
                    : doc.approval_status === 'approved'
                      ? 'border-emerald-400 hover:border-brand-700'
                      : hasUnread(doc) || doc.has_unresolved_violations
                        ? 'border-amber-300 hover:border-brand-700'
                        : 'border-slate-200 hover:border-brand-700'
                }`}
              >
                <div className="flex items-start justify-between gap-1">
                  <div className="flex items-start gap-1.5 min-w-0">
                    <span className={`w-2 h-2 rounded-full shrink-0 mt-1.5 ${STATUS_DOT[doc.status] ?? 'bg-slate-300'}`} />
                    <p className="font-medium text-sm break-words whitespace-normal">{doc.original_filename}</p>
                  </div>
                  {hasUnread(doc) && (
                    <span className="w-2 h-2 rounded-full bg-red-500 shrink-0 mt-1.5" />
                  )}
                </div>
                <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                  <p className="text-xs text-slate-500">{STATUS_LABELS[doc.status] ?? doc.status}</p>
                  {doc.approval_status && (
                    <span className={`text-[10px] uppercase tracking-wide font-medium px-1.5 py-0.5 rounded ${APPROVAL_BADGE[doc.approval_status] ?? 'bg-gray-100 text-gray-600'}`}>
                      {APPROVAL_LABELS[doc.approval_status] ?? doc.approval_status}
                    </span>
                  )}
                </div>
                {doc.owner_full_name && (
                  <p className="text-xs text-slate-400 mt-0.5 truncate">{doc.owner_full_name}</p>
                )}
              </button>
            ))}
          </div>

          {/* ── Мобильный экран деталей ── */}
          {mobileShowDetail && selectedDoc && (
            <div className="md:hidden flex-1 flex flex-col overflow-hidden">
              {/* Мобильные вкладки */}
              <div className="shrink-0 flex border-b bg-white dark:bg-[#1e1e1e] dark:border-[#3a3a3a]">
                <button
                  className={`flex-1 py-2.5 text-xs font-medium border-b-2 -mb-px transition-colors ${!mobilePdfVisible ? 'border-brand-600 text-brand-600' : 'border-transparent text-gray-500'}`}
                  onClick={() => setMobilePdfVisible(false)}
                >
                  Детали
                </button>
                <button
                  className={`flex-1 py-2.5 text-xs font-medium border-b-2 -mb-px transition-colors ${mobilePdfVisible ? 'border-brand-600 text-brand-600' : 'border-transparent text-gray-500'}`}
                  onClick={() => setMobilePdfVisible(true)}
                >
                  Документ
                </button>
              </div>
              {/* PDF */}
              {mobilePdfVisible && (
                <div className="flex-1 overflow-hidden">
                  {previewUrl ? (
                    <PdfPane
                      key={selectedDoc.id}
                      url={previewUrl}
                      label={`${selectedDoc.original_filename}`}
                      highlights={violationHighlights}
                      activeText={activeViolationText}
                      onHighlightClick={(needle) => {
                        const hit = violations.find((v) => violationNeedle(v) === needle);
                        if (hit) selectViolation(hit.id);
                      }}
                    />
                  ) : (
                    <div className="flex-1 flex items-center justify-center text-sm text-slate-400 p-6 text-center">
                      Превью недоступно — документ ещё не обработан.
                    </div>
                  )}
                </div>
              )}
              {/* Детали */}
              {!mobilePdfVisible && (
                <div className="flex-1 overflow-auto">
                  <div className="p-4 border-b border-slate-100 space-y-2">
                    <p className="font-semibold text-sm text-slate-800">{selectedDoc.original_filename}</p>
                    {selectedDoc.owner_full_name && (
                      <p className="text-xs text-slate-400">{selectedDoc.owner_full_name}</p>
                    )}
                    {report && (
                      <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs text-slate-600">
                        <span>Замечаний: <b>{report.total_violations}</b></span>
                        <span>Автоисправлено: <b>{report.auto_fixed}</b></span>
                        <span>Вручную: <b>{report.manual_required}</b></span>
                      </div>
                    )}
                    {selectedDoc.status === 'done' && (
                      <div className="flex flex-wrap gap-1.5">
                        <button
                          onClick={() => downloadViaApi(
                            `/documents/${selectedDoc.id}/download/processed`,
                            `processed_${selectedDoc.original_filename ?? selectedDoc.id}.docx`
                          )}
                          className="btn-secondary text-xs py-1 px-2"
                        >
                          Исправленный .docx
                        </button>
                        <button
                          onClick={async () => {
                            try {
                              const res = await api.get(`/documents/${selectedDoc.id}/report?format=pdf`, { responseType: 'blob' });
                              const blobUrl = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
                              const win = window.open(blobUrl, '_blank');
                              if (win) win.addEventListener('load', () => URL.revokeObjectURL(blobUrl), { once: true });
                              else setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
                            } catch (err) {
                              alert(getApiErrorMessage(err, 'Ошибка загрузки отчёта'));
                            }
                          }}
                          className="btn-secondary text-xs py-1 px-2"
                        >
                          Отчёт .pdf
                        </button>
                      </div>
                    )}
                  </div>
                  {/* Табы решения/замечаний/переписки */}
                  <div className="flex border-b border-slate-100">
                    {TABS.map((t) => (
                      <button
                        key={t.id}
                        onClick={() => {
                          setActiveTab(t.id);
                          if (t.id === 'chat' && selectedDoc) markSeen(selectedDoc.id);
                        }}
                        className={`flex-1 text-xs py-2 font-medium transition-colors relative ${
                          activeTab === t.id
                            ? 'border-b-2 border-brand-600 text-brand-700'
                            : 'text-slate-500 hover:text-slate-700'
                        }`}
                      >
                        {t.label}
                        {t.badge && activeTab !== t.id && (
                          <span className="absolute top-1.5 right-2 w-1.5 h-1.5 rounded-full bg-red-500" />
                        )}
                      </button>
                    ))}
                  </div>
                  {activeTab === 'decision' && (
                    <div className="p-4 space-y-4">
                      {!selectedDoc.approval_status && (
                        <p className="text-sm text-slate-400">Студент ещё не отправил документ на проверку.</p>
                      )}
                      {selectedDoc.approval_status && selectedDoc.approval_status !== 'pending_review' && (
                        <div className="space-y-1">
                          <span className={`badge text-xs ${APPROVAL_BADGE[selectedDoc.approval_status]}`}>
                            {APPROVAL_LABELS[selectedDoc.approval_status]}
                          </span>
                          {selectedDoc.approval_comment && (
                            <p className="text-xs text-slate-600 whitespace-pre-wrap bg-slate-50 rounded px-2 py-1.5">
                              «{selectedDoc.approval_comment}»
                            </p>
                          )}
                        </div>
                      )}
                      {canDecide && (
                        <div className="space-y-2">
                          <p className="text-xs text-amber-700 font-medium">Документ ожидает вашего решения</p>
                          <textarea
                            className="input w-full text-sm"
                            rows={3}
                            placeholder="Комментарий (обязателен для отклонения)"
                            value={decisionComment}
                            onChange={(e) => { setDecisionComment(e.target.value); setDecisionError(''); }}
                            disabled={decisionBusy}
                          />
                          {decisionError && <p className="text-xs text-red-700">{decisionError}</p>}
                          <div className="flex gap-2">
                            <button
                              type="button"
                              className="btn-primary text-sm py-1.5 px-4 disabled:opacity-50"
                              onClick={() => decide('approve')}
                              disabled={decisionBusy}
                            >
                              {decisionBusy ? '…' : 'Принять'}
                            </button>
                            <button
                              type="button"
                              className="text-sm py-1.5 px-4 rounded-xl border border-red-200 text-red-700 hover:bg-red-50 disabled:opacity-50"
                              onClick={() => decide('reject')}
                              disabled={decisionBusy}
                            >
                              Отклонить
                            </button>
                          </div>
                        </div>
                      )}
                      <div>
                        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">История решений</p>
                        <ReviewHistory documentId={selectedDocId} />
                      </div>
                    </div>
                  )}
                  {activeTab === 'violations' && (
                    <ViolationsList
                      documentId={selectedDocId}
                      currentUser={currentUser}
                      violations={violations}
                      setViolations={setViolations}
                      activeId={activeViolationId}
                      onSelect={selectViolation}
                    />
                  )}
                  {activeTab === 'chat' && (
                    <div className="min-h-0">
                      <CommentThread documentId={selectedDocId} currentUser={currentUser} />
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* ── Двухколоночный layout (только desktop) ── */}
          <div className="hidden md:grid flex-1 gap-4 px-8 pb-6 overflow-hidden"
            style={{ gridTemplateColumns: 'minmax(260px,300px) 1fr' }}>

            {/* Колонка 1: список документов — без изменений */}
            <div className="card flex flex-col overflow-hidden">
              <div className="mb-2 flex items-center justify-between shrink-0">
                <h2 className="text-base font-semibold">Документы</h2>
                <span className="text-xs text-slate-400">{visibleDocuments.length} из {documents.length}</span>
              </div>
              <div className="shrink-0 space-y-1.5 mb-2">
                <input
                  type="text"
                  value={docQuery}
                  onChange={(e) => setDocQuery(e.target.value)}
                  placeholder="Поиск: файл или студент"
                  className="input py-1 px-2 text-xs w-full"
                />
                <div className="flex gap-1.5">
                  <select
                    value={docStatusFilter}
                    onChange={(e) => setDocStatusFilter(e.target.value)}
                    className="input py-1 px-1.5 text-xs flex-1"
                    title="Фильтр по статусу проверки"
                  >
                    <option value="all">Все статусы</option>
                    <option value="pending_review">На проверке</option>
                    <option value="approved">Принят</option>
                    <option value="rejected">Отклонён</option>
                  </select>
                  <select
                    value={docSort}
                    onChange={(e) => setDocSort(e.target.value)}
                    className="input py-1 px-1.5 text-xs flex-1"
                    title="Сортировка"
                  >
                    <option value="status">По статусу</option>
                    <option value="date">По дате</option>
                    <option value="name">По имени</option>
                  </select>
                </div>
              </div>
              <div className="flex-1 overflow-auto space-y-2 pr-1">
                {visibleDocuments.length === 0 && (
                  <p className="text-sm text-slate-500">
                    {documents.length === 0 ? 'Загруженных работ ещё нет.' : 'Ничего не найдено.'}
                  </p>
                )}
                {visibleDocuments.map((doc) => (
                  <button
                    key={doc.id}
                    onClick={() => openReport(doc.id)}
                    className={`w-full rounded-xl border bg-white p-3 text-left transition-colors ${
                      selectedDocId === doc.id
                        ? 'border-brand-700 bg-brand-50/40'
                        : doc.approval_status === 'approved'
                          ? 'border-emerald-400 hover:border-brand-700'
                          : hasUnread(doc) || doc.has_unresolved_violations
                            ? 'border-amber-300 hover:border-brand-700'
                            : 'border-slate-200 hover:border-brand-700'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-1">
                      <div className="flex items-start gap-1.5 min-w-0">
                        <span
                          className={`w-2 h-2 rounded-full shrink-0 mt-1.5 ${STATUS_DOT[doc.status] ?? 'bg-slate-300'}`}
                          title={STATUS_LABELS[doc.status] ?? doc.status}
                        />
                        <p className="font-medium text-sm break-words whitespace-normal">{doc.original_filename}</p>
                      </div>
                      {hasUnread(doc) && (
                        <span className="w-2 h-2 rounded-full bg-red-500 shrink-0 mt-1.5" title="Новое сообщение" />
                      )}
                    </div>
                    <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                      <p className="text-xs text-slate-500">{STATUS_LABELS[doc.status] ?? doc.status}</p>
                      {doc.approval_status && (
                        <span className={`text-[10px] uppercase tracking-wide font-medium px-1.5 py-0.5 rounded ${APPROVAL_BADGE[doc.approval_status] ?? 'bg-gray-100 text-gray-600'}`}>
                          {APPROVAL_LABELS[doc.approval_status] ?? doc.approval_status}
                        </span>
                      )}
                      {doc.has_unresolved_violations && (
                        <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-amber-100 text-amber-800">замечания</span>
                      )}
                    </div>
                    {doc.owner_full_name && (
                      <p className="text-xs text-slate-400 mt-0.5 truncate">{doc.owner_full_name}</p>
                    )}
                    {doc.uploaded_at && (
                      <p className="text-[11px] text-slate-400 mt-0.5">{formatDocDate(doc.uploaded_at)}</p>
                    )}
                  </button>
                ))}
              </div>
            </div>

            {/* Колонка 2: детальный вид — как у студента */}
            {!selectedDoc ? (
              <div className="card flex items-center justify-center">
                <p className="text-sm text-slate-400">Выберите документ, чтобы посмотреть его превью.</p>
              </div>
            ) : (
              <div className="flex flex-col overflow-hidden rounded-xl bg-white dark:bg-[#1e1e1e] shadow-panel">

                {/* Шапка — как у студента */}
                <div className="shrink-0 flex items-center gap-2 px-4 py-2 border-b border-slate-100 dark:border-[#3a3a3a] bg-white dark:bg-[#1e1e1e]">
                  <div className="min-w-0 flex-shrink">
                    <h1 className="text-sm font-semibold text-gray-900 truncate">{selectedDoc.original_filename}</h1>
                    {selectedDoc.owner_full_name && (
                      <p className="text-[11px] text-slate-400 leading-tight">{selectedDoc.owner_full_name}</p>
                    )}
                  </div>
                  {selectedDoc.approval_status && (
                    <span className={`badge text-xs shrink-0 ${APPROVAL_BADGE[selectedDoc.approval_status] ?? 'bg-gray-100 text-gray-600'}`}>
                      {APPROVAL_LABELS[selectedDoc.approval_status]}
                    </span>
                  )}
                  <div className="ml-auto flex items-center gap-1.5 shrink-0">
                    {selectedDoc.status === 'done' && (
                      <>
                        <button
                          onClick={() => downloadViaApi(
                            `/documents/${selectedDoc.id}/download/processed`,
                            `processed_${selectedDoc.original_filename ?? selectedDoc.id}.docx`
                          )}
                          className="btn-secondary text-xs py-1 px-2"
                        >
                          .docx
                        </button>
                        <button
                          onClick={async () => {
                            try {
                              const res = await api.get(`/documents/${selectedDoc.id}/report?format=pdf`, { responseType: 'blob' });
                              const blobUrl = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
                              const win = window.open(blobUrl, '_blank');
                              if (win) win.addEventListener('load', () => URL.revokeObjectURL(blobUrl), { once: true });
                              else setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
                            } catch (err) {
                              alert(getApiErrorMessage(err, 'Ошибка загрузки отчёта'));
                            }
                          }}
                          className="btn-secondary text-xs py-1 px-2"
                        >
                          Отчёт
                        </button>
                      </>
                    )}
                    <NormativeDocsButton />
                  </div>
                </div>

                {/* Тело: PDF слева + панель справа */}
                <div className="flex-1 flex overflow-hidden">

                  {/* PDF */}
                  <div className="flex-1 overflow-hidden">
                    {previewUrl ? (
                      <PdfPane
                        key={selectedDoc.id}
                        url={previewUrl}
                        label={`Исправленный: ${selectedDoc.original_filename}`}
                        highlights={violationHighlights}
                        activeText={activeViolationText}
                        onHighlightClick={(needle) => {
                          const hit = violations.find((v) => violationNeedle(v) === needle);
                          if (hit) selectViolation(hit.id);
                        }}
                      />
                    ) : (
                      <div className="h-full flex items-center justify-center text-sm text-slate-400 p-6 text-center">
                        Превью недоступно — документ ещё не обработан.
                      </div>
                    )}
                  </div>

                  {/* Drag-разделитель */}
                  <div
                    ref={dragRef}
                    className="shrink-0 w-1.5 cursor-col-resize flex items-center justify-center bg-transparent hover:bg-brand-100 active:bg-brand-200 transition-colors group z-10"
                    onMouseDown={onDividerMouseDown}
                  >
                    <div className="w-0.5 h-8 rounded-full bg-gray-300 group-hover:bg-brand-400 transition-colors" />
                  </div>

                  {/* Правая панель */}
                  <div className="shrink-0 flex flex-col overflow-hidden bg-white dark:bg-[#252525]" style={{ width: panelWidth }}>

                    {/* Статистика */}
                    {report && (
                      <div className="shrink-0 px-4 py-2 border-b border-slate-100 dark:border-[#3a3a3a]">
                        <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs text-slate-600">
                          <span>Замечаний: <b>{report.total_violations}</b></span>
                          <span>Автоисправлено: <b>{report.auto_fixed}</b></span>
                          <span>Вручную: <b>{report.manual_required}</b></span>
                          {report.volume_pages != null && <span>Объём: ~<b>{report.volume_pages}</b> стр.</span>}
                        </div>
                      </div>
                    )}

                    {/* Табы */}
                    <div className="shrink-0 flex border-b border-slate-100 dark:border-[#3a3a3a]">
                      {TABS.map((t) => (
                        <button
                          key={t.id}
                          onClick={() => {
                            setActiveTab(t.id);
                            if (t.id === 'chat' && selectedDoc) markSeen(selectedDoc.id);
                          }}
                          className={`flex-1 text-xs py-2.5 font-medium transition-colors relative ${
                            activeTab === t.id
                              ? 'border-b-2 border-brand-600 text-brand-700'
                              : 'text-slate-500 hover:text-slate-700'
                          }`}
                        >
                          {t.label}
                          {t.badge && activeTab !== t.id && (
                            <span className="absolute top-1.5 right-2 w-1.5 h-1.5 rounded-full bg-red-500" />
                          )}
                        </button>
                      ))}
                    </div>

                    {/* Контент таба */}
                    <div className="flex-1 overflow-auto">

                      {activeTab === 'decision' && (
                        <div className="p-4 space-y-4">
                          {!selectedDoc.approval_status && (
                            <p className="text-sm text-slate-400">Студент ещё не отправил документ на проверку.</p>
                          )}
                          {selectedDoc.approval_status && selectedDoc.approval_status !== 'pending_review' && (
                            <div className="space-y-1">
                              <div className="flex items-center gap-2">
                                <span className={`badge text-xs ${APPROVAL_BADGE[selectedDoc.approval_status]}`}>
                                  {APPROVAL_LABELS[selectedDoc.approval_status]}
                                </span>
                                {selectedDoc.approval_decided_at && (
                                  <span className="text-xs text-slate-400">{fmtDate(selectedDoc.approval_decided_at)}</span>
                                )}
                              </div>
                              {selectedDoc.approval_comment && (
                                <p className="text-xs text-slate-600 whitespace-pre-wrap bg-slate-50 dark:bg-[#2a2a2a] rounded px-2 py-1.5">
                                  «{selectedDoc.approval_comment}»
                                </p>
                              )}
                            </div>
                          )}
                          {canDecide && (
                            <div className="space-y-2">
                              <p className="text-xs text-amber-700 font-medium">Документ ожидает вашего решения</p>
                              <textarea
                                className="input w-full text-sm"
                                rows={3}
                                placeholder="Комментарий (обязателен для отклонения)"
                                value={decisionComment}
                                onChange={(e) => { setDecisionComment(e.target.value); setDecisionError(''); }}
                                disabled={decisionBusy}
                              />
                              {decisionError && <p className="text-xs text-red-700">{decisionError}</p>}
                              <div className="flex gap-2">
                                <button
                                  type="button"
                                  className="btn-primary text-sm py-1.5 px-4 disabled:opacity-50"
                                  onClick={() => decide('approve')}
                                  disabled={decisionBusy}
                                >
                                  {decisionBusy ? '…' : 'Принять'}
                                </button>
                                <button
                                  type="button"
                                  className="text-sm py-1.5 px-4 rounded-xl border border-red-200 text-red-700 hover:bg-red-50 disabled:opacity-50"
                                  onClick={() => decide('reject')}
                                  disabled={decisionBusy}
                                >
                                  Отклонить
                                </button>
                              </div>
                            </div>
                          )}
                          <div>
                            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">История решений</p>
                            <ReviewHistory documentId={selectedDocId} />
                          </div>
                        </div>
                      )}

                      {activeTab === 'violations' && (
                        <ViolationsList
                          documentId={selectedDocId}
                          currentUser={currentUser}
                          violations={violations}
                          setViolations={setViolations}
                          activeId={activeViolationId}
                          onSelect={selectViolation}
                        />
                      )}

                      {activeTab === 'chat' && (
                        <div className="h-full flex flex-col">
                          <CommentThread documentId={selectedDocId} currentUser={currentUser} />
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </Layout>
  );
}

export default StaffPage;
