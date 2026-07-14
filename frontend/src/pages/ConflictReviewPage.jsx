import React, { useEffect, useMemo, useState } from 'react';
import PdfPane from '../components/PdfPane';
import SnapshotHistory from '../components/SnapshotHistory';
import getApiErrorMessage from '../utils/errorMessage';
import { violationNeedle } from '../utils/violationAnchor';
import usePreviewRefresh from '../utils/usePreviewRefresh';

// ── Карточка конфликта ────────────────────────────────────────────────────────

const CUSTOM = '__custom__';

// Тип элемента, который пользователь подтверждает.
const KIND_HEADING = 'heading';
const KIND_TEXT    = 'text';
const KIND_LIST    = 'list';

function ConflictCard({
  conflict,
  kind,
  chosen,
  customNumber,
  onChooseKind,
  onChoose,
  onCustomChange,
  onApply,
  isActive,
  onActivate,
  disabled,
  busy,
}) {
  const options = conflict.fix_options ?? [];
  // options[0] — исходный (возможно неверный) номер; оставить как есть
  // options[1] — ожидаемый номер на том же уровне; рекомендуемое исправление
  // options[2] — ожидаемый номер на соседнем уровне (необязателен)
  const optionLabels = [
    'оставить (снять замечание)',
    'заменить ← рекомендуется',
    'заменить (соседний уровень)',
  ];
  const effectiveChosen = chosen ?? options[1] ?? options[0];
  const effectiveKind = kind ?? KIND_HEADING;

  const KindRadio = ({ value, label, hint }) => (
    <label className="flex items-start gap-2 cursor-pointer text-sm">
      <input
        type="radio"
        name={`kind-${conflict.id}`}
        value={value}
        checked={effectiveKind === value}
        onChange={() => onChooseKind(value)}
        className="mt-0.5 accent-blue-600"
        onClick={(e) => e.stopPropagation()}
      />
      <span>
        <span className="font-medium text-gray-800">{label}</span>
        {hint && <span className="text-gray-400 text-xs"> — {hint}</span>}
      </span>
    </label>
  );

  return (
    <div
      className={`rounded-xl border p-4 space-y-3 cursor-pointer transition-colors ${
        isActive ? 'border-blue-400 bg-blue-50' : 'border-gray-200 hover:border-gray-300'
      }`}
      onClick={onActivate}
    >
      <p className="text-sm font-medium text-gray-800 break-words">{conflict.section_title}</p>
      <p className="text-xs text-gray-500">{conflict.description}</p>

      <div className="space-y-1.5 pt-1 border-t border-gray-100">
        <p className="text-xs uppercase tracking-wide text-gray-400 pt-2">Что это?</p>
        <KindRadio value={KIND_HEADING} label="Заголовок"           hint="оформить как раздел/подраздел" />
        <KindRadio value={KIND_TEXT}    label="Обычный текст"        hint="это абзац, не заголовок" />
        <KindRadio value={KIND_LIST}    label="Пункт списка"         hint="строка нумерованного перечисления" />
      </div>

      {effectiveKind === KIND_HEADING && (
        <div className="space-y-1.5 pt-2 border-t border-gray-100">
          <p className="text-xs uppercase tracking-wide text-gray-400">Номер заголовка</p>
          {options.map((opt, idx) => (
            <label key={opt} className="flex items-start gap-2 cursor-pointer text-sm">
              <input
                type="radio"
                name={`fix-${conflict.id}`}
                value={opt}
                checked={effectiveChosen === opt}
                onChange={() => onChoose(opt)}
                className="mt-0.5 accent-blue-600"
                onClick={(e) => e.stopPropagation()}
              />
              <span>
                <span className="font-mono font-semibold bg-gray-100 px-1 rounded">{opt}</span>{' '}
                <span className="text-gray-400 text-xs">{optionLabels[idx] ?? ''}</span>
              </span>
            </label>
          ))}
          <label className="flex items-center gap-2 cursor-pointer text-sm">
            <input
              type="radio"
              name={`fix-${conflict.id}`}
              value={CUSTOM}
              checked={effectiveChosen === CUSTOM}
              onChange={() => onChoose(CUSTOM)}
              className="accent-blue-600"
              onClick={(e) => e.stopPropagation()}
            />
            <span className="text-gray-700">Свой номер:</span>
            <input
              type="text"
              inputMode="decimal"
              placeholder="2.1.3"
              value={customNumber ?? ''}
              onClick={(e) => { e.stopPropagation(); onChoose(CUSTOM); }}
              onChange={(e) => onCustomChange(e.target.value)}
              className="input py-0.5 px-2 text-xs font-mono w-24"
            />
          </label>
        </div>
      )}

      <button
        className="btn-primary py-1 px-3 text-sm w-full disabled:opacity-50 disabled:cursor-not-allowed"
        disabled={disabled}
        onClick={(e) => { e.stopPropagation(); onApply(); }}
      >
        {busy ? 'Применяю…' : 'Применить'}
      </button>
    </div>
  );
}

// ── Главный компонент ─────────────────────────────────────────────────────────

export default function ConflictReviewPage({
  doc,
  violations: initialViolations,
  onBack,
  onApplyFix,
  onDemoteHeading,
  onRefreshViolations,
}) {
  const [violations, setViolations] = useState(initialViolations);
  const [chosen, setChosen]         = useState({});
  const [customNumbers, setCustomNumbers] = useState({});
  const [kinds, setKinds]           = useState({});
  const [activeId, setActiveId]     = useState(null);
  const [showHistory, setShowHistory] = useState(false);
  // Per-card блокировка вместо глобальной: applyingId === id той карточки,
  // у которой сейчас летит запрос. Остальные карточки тоже disabled (после
  // ответа сервер пришлёт обновлённый список violations — старые id из других
  // карточек могут устареть, allowing parallel applies даст race condition,
  // защитой от которого служит S-07 lock на бэке, но UX из этого хороший
  // не сделать). При этом spinner и текст «Применяю…» отображаются только
  // на конкретной карточке — пользователь видит, где идёт работа.
  const [applyingId, setApplyingId] = useState(null);
  const [toast, setToast]           = useState('');
  const [pdfVersion, bustPreview] = usePreviewRefresh(doc.id);

  const showToast = (msg) => { setToast(msg); setTimeout(() => setToast(''), 3500); };

  const conflicts = violations.filter(
    (v) => v.type === 'heading_number_conflict' && v.status === 'manual_required',
  );
  const activeConflict = conflicts.find((v) => v.id === activeId) ?? null;

  // A-D2 — группируем конфликты в каскады. Если студент написал «1.5»
  // вместо «1.1», все последующие заголовки тоже сдвинутся и backend
  // пометит их как caused_by_index = paragraph_index первого. Показываем
  // root отдельной карточкой; «дети» прячем под раскрывашку, чтобы юзер
  // не пугался списка из 15 одинаковых нарушений и сосредоточился на корне.
  const cascadeGroups = useMemo(() => {
    const byRoot = new Map();   // paragraph_index → root violation
    const childrenOf = new Map(); // paragraph_index → child violations
    for (const v of conflicts) {
      if (v.caused_by_index == null) {
        byRoot.set(v.paragraph_index, v);
      } else {
        if (!childrenOf.has(v.caused_by_index)) childrenOf.set(v.caused_by_index, []);
        childrenOf.get(v.caused_by_index).push(v);
      }
    }
    // Если каскадный нашёлся, но root уже исправлен (его нет в conflicts),
    // показываем такие как самостоятельные — иначе они исчезнут из UI.
    const orphans = [];
    for (const [rootIdx, kids] of childrenOf.entries()) {
      if (!byRoot.has(rootIdx)) {
        for (const k of kids) orphans.push(k);
      }
    }
    return {
      roots: Array.from(byRoot.values()).map((root) => ({
        root,
        children: childrenOf.get(root.paragraph_index) ?? [],
      })),
      orphans,
    };
  }, [conflicts]);

  const [expandedRoots, setExpandedRoots] = useState(() => new Set());
  const toggleExpanded = (rootId) => {
    setExpandedRoots((prev) => {
      const next = new Set(prev);
      if (next.has(rootId)) next.delete(rootId); else next.add(rootId);
      return next;
    });
  };

  // Автоматически выбираем первый конфликт только на первом mount'е. Явный
  // null после этого означает "пользователь снял выделение" — не перетираем.
  const [autoSelected, setAutoSelected] = useState(false);
  useEffect(() => {
    if (!autoSelected && conflicts.length > 0 && activeId === null) {
      setActiveId(conflicts[0].id);
      setAutoSelected(true);
    }
  }, [conflicts.length, autoSelected, activeId]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') setActiveId(null); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const toggleActive = (id) => setActiveId((prev) => (prev === id ? null : id));

  // Якорный текст конфликта (см. utils/violationAnchor): для заголовков это
  // полный section_title — он уникальнее короткого числового префикса.
  const highlightTexts = useMemo(
    () => conflicts.map(violationNeedle).filter(Boolean),
    [conflicts],
  );
  const activeText = violationNeedle(activeConflict);

  const handleApply = async (conflictId) => {
    const conflict = conflicts.find((v) => v.id === conflictId);
    if (!conflict) return;
    const kind = kinds[conflictId] ?? KIND_HEADING;

    setApplyingId(conflictId);
    try {
      if (kind === KIND_HEADING) {
        const choice = chosen[conflictId] ?? conflict.fix_options?.[1] ?? conflict.fix_options?.[0];
        let chosenNumber = choice;
        if (choice === CUSTOM) {
          const raw = (customNumbers[conflictId] || '').trim();
          if (!/^\d+(\.\d+){0,2}$/.test(raw)) {
            showToast('Свой номер должен быть в формате 1, 1.2 или 1.2.3');
            return;
          }
          chosenNumber = raw;
        }
        if (!chosenNumber) return;
        await onApplyFix(conflictId, chosenNumber);
      } else {
        // KIND_TEXT или KIND_LIST — обе ветки делают одну OXML-мутацию
        // (понижение в body-абзац), различие фиксируется на бэкенде в
        // violation.fixed_text для отчёта.
        if (typeof onDemoteHeading !== 'function') {
          showToast('Действие недоступно: нет обработчика onDemoteHeading');
          return;
        }
        await onDemoteHeading(conflictId, kind);
      }

      const updated = await onRefreshViolations(doc.id);
      setViolations(updated);
      bustPreview();
      const remaining = updated.filter(
        (v) => v.type === 'heading_number_conflict' && v.status === 'manual_required',
      );
      if (remaining.length > 0) {
        setActiveId(remaining[0].id);
        showToast(`Применено. Осталось конфликтов: ${remaining.length}`);
      } else {
        showToast('Все конфликты нумерации разрешены!');
        setActiveId(null);
      }
    } catch (err) {
      showToast(getApiErrorMessage(err, 'Ошибка при применении исправления'));
    } finally {
      setApplyingId(null);
    }
  };

  const originalUrl  = `/api/v1/documents/${doc.id}/preview/original`;
  const processedUrl = `/api/v1/documents/${doc.id}/preview/processed?v=${pdfVersion}`;

  return (
    <div className="flex flex-col" style={{ height: '100vh' }}>
      {toast && (
        <div className="fixed top-4 right-4 z-50 bg-white border border-gray-200 shadow-lg rounded-xl px-4 py-3 text-sm text-gray-800 max-w-sm">
          {toast}
        </div>
      )}

      {/* История изменений (drawer) */}
      {showHistory && (
        <SnapshotHistory
          documentId={doc.id}
          onRollback={async () => {
            const updated = await onRefreshViolations(doc.id);
            setViolations(updated);
            bustPreview();
            setShowHistory(false);
          }}
          onClose={() => setShowHistory(false)}
        />
      )}

      {/* Шапка */}
      <div className="shrink-0 flex items-center gap-4 px-6 py-3 border-b bg-white">
        <button className="text-sm text-gray-500 hover:text-gray-700" onClick={onBack}>← Назад</button>
        <div className="flex-1 min-w-0">
          <h2 className="font-semibold text-gray-900 truncate">{doc.original_filename}</h2>
          <p className="text-xs text-gray-400">Разрешение конфликтов нумерации</p>
        </div>
        <button
          className="text-sm text-gray-400 hover:text-gray-600 border border-gray-200 rounded-lg px-2.5 py-1 hover:bg-gray-50 transition-colors"
          onClick={() => setShowHistory(true)}
          title="История изменений"
        >
          ↺ История
        </button>
        <span className={`text-sm font-medium ${conflicts.length === 0 ? 'text-emerald-600' : 'text-amber-600'}`}>
          {conflicts.length === 0 ? 'Всё исправлено' : `${conflicts.length} конфликт${conflicts.length === 1 ? '' : 'ов'}`}
        </span>
      </div>

      {/* Тело */}
      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 overflow-hidden border-r">
          <PdfPane
            key={`orig-${conflicts.length}-${pdfVersion}`}
            url={originalUrl}
            label="Оригинал"
            highlights={highlightTexts}
            activeText={activeText}
            onHighlightClick={(needle) => {
              const hit = conflicts.find(
                (v) => violationNeedle(v) === needle,
              );
              if (hit) toggleActive(hit.id);
            }}
          />
        </div>
        <div className="flex-1 overflow-hidden border-r">
          {/* key={pdfVersion} форсирует unmount+remount при ручной правке —
              гарантия, что PdfPane сбросит canvas/text-layer и перерендерит
              новый PDF. Без этого useEffect полагается на изменение url, но
              если, например, pdfVersion не сменится (повторное apply того же
              исправления), стоит остаться надёжный fallback. */}
          <PdfPane
            key={pdfVersion}
            url={processedUrl}
            label="Исправленный (авто-правки)"
            highlights={highlightTexts}
            activeText={activeText}
            onHighlightClick={(needle) => {
              const hit = conflicts.find(
                (v) => violationNeedle(v) === needle,
              );
              if (hit) toggleActive(hit.id);
            }}
          />
        </div>

        {/* Боковая панель */}
        <div className="w-80 shrink-0 flex flex-col overflow-hidden">
          <div className="shrink-0 px-4 py-3 border-b bg-gray-50">
            <h3 className="text-sm font-semibold text-gray-700">Конфликты нумерации</h3>
          </div>
          <div className="flex-1 overflow-auto p-4 space-y-3">
            {conflicts.length === 0 && (
              <div className="text-sm text-emerald-600 text-center py-8">✓ Все конфликты разрешены</div>
            )}
            {cascadeGroups.roots.map(({ root, children }) => {
              const expanded = expandedRoots.has(root.id);
              const cardProps = (v) => ({
                key: v.id,
                conflict: v,
                kind: kinds[v.id],
                chosen: chosen[v.id],
                customNumber: customNumbers[v.id],
                onChooseKind: (val) => setKinds((prev) => ({ ...prev, [v.id]: val })),
                onChoose: (val) => setChosen((prev) => ({ ...prev, [v.id]: val })),
                onCustomChange: (val) => setCustomNumbers((prev) => ({ ...prev, [v.id]: val })),
                onApply: () => handleApply(v.id),
                isActive: v.id === activeConflict?.id,
                onActivate: () => toggleActive(v.id),
                disabled: applyingId !== null,
                busy: applyingId === v.id,
              });
              return (
                <div key={root.id} className="space-y-2">
                  <ConflictCard {...cardProps(root)} />
                  {children.length > 0 && (
                    <div className="pl-3 border-l-2 border-amber-200">
                      <button
                        type="button"
                        onClick={() => toggleExpanded(root.id)}
                        className="text-xs text-amber-700 hover:text-amber-900 py-1"
                      >
                        {expanded ? '▾' : '▸'} Связанные нарушения нумерации ({children.length})
                        {!expanded && (
                          <span className="text-gray-400 ml-1">— часто исправляются автоматически после правки выше</span>
                        )}
                      </button>
                      {expanded && (
                        <div className="space-y-2 pt-1 pb-2">
                          {children.map((child) => (
                            <ConflictCard {...cardProps(child)} />
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
            {cascadeGroups.orphans.length > 0 && (
              <div className="pt-2 border-t border-gray-100 space-y-3">
                {cascadeGroups.orphans.map((v) => (
                  <ConflictCard
                    key={v.id}
                    conflict={v}
                    kind={kinds[v.id]}
                    chosen={chosen[v.id]}
                    customNumber={customNumbers[v.id]}
                    onChooseKind={(val) => setKinds((prev) => ({ ...prev, [v.id]: val }))}
                    onChoose={(val) => setChosen((prev) => ({ ...prev, [v.id]: val }))}
                    onCustomChange={(val) => setCustomNumbers((prev) => ({ ...prev, [v.id]: val }))}
                    onApply={() => handleApply(v.id)}
                    isActive={v.id === activeConflict?.id}
                    onActivate={() => toggleActive(v.id)}
                    disabled={applyingId !== null}
                    busy={applyingId === v.id}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
