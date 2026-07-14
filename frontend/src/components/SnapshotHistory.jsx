import React, { useCallback, useEffect, useRef, useState } from 'react';
import api from '../api/client';
import getApiErrorMessage from '../utils/errorMessage';

// ── Утилиты ──────────────────────────────────────────────────────────────────

const ACTION_META = {
  fix_heading_number: { icon: '✎', color: 'text-blue-600',   bg: 'bg-blue-50',   label: 'Изменён номер'        },
  revert_caption:     { icon: '↺', color: 'text-amber-600',  bg: 'bg-amber-50',  label: 'Подпись восстановлена' },
  demote_heading:     { icon: '↓', color: 'text-purple-600', bg: 'bg-purple-50', label: 'Преобразован в текст'  },
  promote_heading:    { icon: '↑', color: 'text-emerald-600',bg: 'bg-emerald-50',label: 'Оформлен как заголовок'},
  revert_auto_fix:    { icon: '↩', color: 'text-rose-600',   bg: 'bg-rose-50',   label: 'Отменено автоисправление' },
  acknowledge:        { icon: '✓', color: 'text-gray-600',   bg: 'bg-gray-50',   label: 'Ознакомлен'           },
  reject:             { icon: '✕', color: 'text-rose-600',   bg: 'bg-rose-50',   label: 'Замечание отклонено'  },
};

const DEFAULT_META = { icon: '●', color: 'text-gray-500', bg: 'bg-gray-50', label: 'Правка' };

function timeAgo(iso) {
  const diff = Math.floor((Date.now() - new Date(iso)) / 1000);
  if (diff < 60)   return 'только что';
  if (diff < 3600) return `${Math.floor(diff / 60)} мин назад`;
  if (diff < 86400)return `${Math.floor(diff / 3600)} ч назад`;
  return new Date(iso).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
}

// ── Компонент ────────────────────────────────────────────────────────────────

/**
 * Панель «История изменений» — выдвижной drawer справа.
 *
 * Принимает:
 *   documentId      — UUID документа
 *   onRollback      — callback(snapshotId) → после успешного отката
 *   onClose         — закрыть панель
 *
 * Управление:
 *   - Кнопка «Отменить последнее» = откат к первому (самому свежему) снимку
 *   - Список снимков с кнопкой «Откатить» у каждого
 *   - Escape закрывает
 */
export default function SnapshotHistory({ documentId, onRollback, onClose }) {
  const [snapshots, setSnapshots] = useState([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);
  const [rolling, setRolling]     = useState(null); // ID снимка, к которому идёт откат
  const [confirmId, setConfirmId] = useState(null); // снимок, ожидающий подтверждения
  const panelRef = useRef(null);

  const load = useCallback(async (signal) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(
        `/documents/${documentId}/snapshots`,
        signal ? { signal } : undefined,
      );
      setSnapshots(res.data);
    } catch (err) {
      if (err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError') return;
      setError(getApiErrorMessage(err, 'Не удалось загрузить историю'));
    } finally {
      // При cancel finally не сбрасывает loading; следующий load() сам
      // переустановит его в true. Не критично, поскольку cancel почти
      // всегда сопровождается размонтированием компонента.
      setLoading(false);
    }
  }, [documentId]);

  useEffect(() => {
    const abort = new AbortController();
    load(abort.signal);
    return () => abort.abort();
  }, [load]);

  // Закрытие по Escape и клику вне панели.
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    const onOutside = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target)) onClose();
    };
    window.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onOutside);
    return () => {
      window.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onOutside);
    };
  }, [onClose]);

  const doRollback = async (snapshotId) => {
    setRolling(snapshotId);
    setConfirmId(null);
    try {
      await api.post(`/documents/${documentId}/snapshots/${snapshotId}/rollback`);
      await load(); // обновляем список (снимки после этого удалены бэкендом)
      onRollback(snapshotId);
    } catch (err) {
      setError(getApiErrorMessage(err, 'Не удалось откатить изменения'));
    } finally {
      setRolling(null);
    }
  };

  const latestSnapshot = snapshots[0] ?? null;

  return (
    // Затемнённый оверлей
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-black/20" />

      {/* Сама панель */}
      <div
        ref={panelRef}
        className="relative z-50 w-96 max-w-full h-full bg-white dark:bg-[#1e1e1e] shadow-2xl flex flex-col"
        style={{ animation: 'slideInRight 0.2s ease-out' }}
      >
        {/* Шапка */}
        <div className="shrink-0 flex items-center justify-between px-5 py-4 border-b bg-gray-50 dark:bg-[#242424] dark:border-[#3a3a3a]">
          <div>
            <h2 className="text-base font-semibold text-gray-900">История изменений</h2>
            <p className="text-xs text-gray-400 mt-0.5">Снимок создаётся перед каждой правкой</p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-xl leading-none"
            aria-label="Закрыть"
          >
            ×
          </button>
        </div>

        {/* Кнопка «Отменить последнее действие» */}
        {latestSnapshot && (
          <div className="shrink-0 px-5 py-3 border-b bg-white dark:bg-[#1e1e1e] dark:border-[#3a3a3a]">
            {confirmId === latestSnapshot.id ? (
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-600 flex-1">
                  Откатить «{latestSnapshot.action_description}»?
                </span>
                <button
                  className="text-xs px-3 py-1.5 bg-red-500 text-white rounded-lg hover:bg-red-600 disabled:opacity-50"
                  disabled={rolling === latestSnapshot.id}
                  onClick={() => doRollback(latestSnapshot.id)}
                >
                  {rolling === latestSnapshot.id ? '...' : 'Да, откатить'}
                </button>
                <button
                  className="text-xs px-3 py-1.5 border border-gray-300 rounded-lg hover:bg-gray-50"
                  onClick={() => setConfirmId(null)}
                >
                  Отмена
                </button>
              </div>
            ) : (
              <button
                className="w-full flex items-center gap-2 px-3 py-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-sm text-gray-700 disabled:opacity-40"
                disabled={rolling !== null}
                onClick={() => setConfirmId(latestSnapshot.id)}
              >
                <span className="text-base">↩</span>
                <span className="flex-1 text-left truncate">
                  Отменить: <span className="text-gray-500">{latestSnapshot.action_description}</span>
                </span>
              </button>
            )}
          </div>
        )}

        {/* Список снимков */}
        <div className="flex-1 overflow-y-auto">
          {loading && (
            <div className="flex items-center justify-center py-16 text-sm text-gray-400">
              Загрузка…
            </div>
          )}
          {error && !loading && (
            <div className="px-5 py-4 text-sm text-red-500">{error}</div>
          )}
          {!loading && !error && snapshots.length === 0 && (
            <div className="flex flex-col items-center justify-center py-16 text-center px-6">
              <span className="text-4xl mb-3">📋</span>
              <p className="text-sm font-medium text-gray-700">История пуста</p>
              <p className="text-xs text-gray-400 mt-1">
                Снимки появятся после первой ручной правки нарушения
              </p>
            </div>
          )}
          {!loading && !error && snapshots.length > 0 && (
            <div className="relative px-5 py-4">
              {/* Вертикальная линия таймлайна */}
              <div className="absolute left-9 top-4 bottom-4 w-px bg-gray-200" />

              <ol className="space-y-1">
                {snapshots.map((snap, idx) => {
                  const meta = ACTION_META[snap.action_type] ?? DEFAULT_META;
                  const isFirst = idx === 0;
                  const isRolling = rolling === snap.id;
                  const isConfirm = confirmId === snap.id && snap.id !== latestSnapshot?.id;

                  return (
                    <li key={snap.id} className="relative flex gap-3 group">
                      {/* Иконка на таймлайне */}
                      <div
                        className={`shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium border-2 z-10 ${
                          isFirst
                            ? `${meta.bg} ${meta.color} border-current`
                            : 'bg-white text-gray-400 border-gray-200'
                        }`}
                      >
                        {meta.icon}
                      </div>

                      {/* Содержимое карточки */}
                      <div
                        className={`flex-1 min-w-0 rounded-xl border px-3 py-2.5 mb-1 transition-colors ${
                          isFirst
                            ? 'border-gray-300 bg-white shadow-sm'
                            : 'border-gray-100 bg-gray-50/60 hover:bg-white'
                        }`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0 flex-1">
                            <span className={`text-xs font-medium ${meta.color}`}>{meta.label}</span>
                            <p className="text-xs text-gray-700 mt-0.5 break-words leading-relaxed">
                              {snap.action_description}
                            </p>
                            <p className="text-[11px] text-gray-400 mt-1">{timeAgo(snap.created_at)}</p>
                          </div>

                          {/* Кнопка отката */}
                          {isFirst ? null : (
                            <div className="shrink-0 pt-0.5">
                              {isConfirm ? (
                                <div className="flex flex-col gap-1">
                                  <button
                                    className="text-[11px] px-2 py-1 bg-red-500 text-white rounded-md hover:bg-red-600 disabled:opacity-50"
                                    disabled={isRolling}
                                    onClick={(e) => { e.stopPropagation(); doRollback(snap.id); }}
                                  >
                                    {isRolling ? '…' : 'Да'}
                                  </button>
                                  <button
                                    className="text-[11px] px-2 py-1 border border-gray-200 rounded-md hover:bg-gray-100"
                                    onClick={(e) => { e.stopPropagation(); setConfirmId(null); }}
                                  >
                                    Нет
                                  </button>
                                </div>
                              ) : (
                                <button
                                  className="opacity-0 group-hover:opacity-100 text-[11px] px-2 py-1 border border-gray-200 rounded-md hover:bg-gray-100 text-gray-500 transition-opacity disabled:opacity-30"
                                  disabled={rolling !== null}
                                  onClick={(e) => { e.stopPropagation(); setConfirmId(snap.id); }}
                                  title="Откатить к этому состоянию"
                                >
                                  ↩
                                </button>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ol>

              {/* Нижняя метка «Начало» */}
              <div className="flex gap-3 mt-1">
                <div className="shrink-0 w-8 h-8 rounded-full flex items-center justify-center bg-gray-100 border-2 border-gray-200 z-10">
                  <span className="text-xs text-gray-400">▷</span>
                </div>
                <div className="flex items-center">
                  <span className="text-xs text-gray-400">Начальное состояние после обработки</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      <style>{`
        @keyframes slideInRight {
          from { transform: translateX(100%); }
          to   { transform: translateX(0); }
        }
      `}</style>
    </div>
  );
}
