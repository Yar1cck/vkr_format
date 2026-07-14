import React, { useCallback, useEffect, useRef, useState } from 'react';
import api from '../api/client';
import getApiErrorMessage from '../utils/errorMessage';

export default function ParagraphEditor({ documentId, paragraphIndex, initialText, onSaved, onCancel }) {
  const [text, setText] = useState(initialText ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const textareaRef = useRef(null);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
  }, []);

  const handleSave = useCallback(async () => {
    const trimmed = text.trim();
    if (!trimmed) {
      setError('Текст не может быть пустым');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.patch(`/documents/${documentId}/paragraphs/${paragraphIndex}`, { text: trimmed });
      onSaved(trimmed);
    } catch (e) {
      setError(getApiErrorMessage(e, 'Не удалось сохранить'));
    } finally {
      setSaving(false);
    }
  }, [text, documentId, paragraphIndex, onSaved]);

  const handleKeyDown = useCallback((e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); handleSave(); }
    if (e.key === 'Escape') onCancel();
  }, [handleSave, onCancel]);

  return (
    <div className="mt-2 rounded-lg border border-blue-200 bg-blue-50/40 overflow-hidden" onClick={(e) => e.stopPropagation()}>
      <textarea
        ref={textareaRef}
        className="paragraph-editor-content w-full resize-none bg-transparent px-3 py-2 text-sm outline-none"
        rows={4}
        spellCheck
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
      />
      {error && <p className="text-xs text-red-600 px-3 pb-1">{error}</p>}
      <div className="flex items-center gap-2 px-3 py-2 border-t border-blue-100 bg-white">
        <button
          type="button"
          className="btn-primary py-1 px-3 text-xs disabled:opacity-50"
          disabled={saving}
          onClick={handleSave}
        >
          {saving ? 'Сохраняю…' : 'Сохранить'}
        </button>
        <button
          type="button"
          className="btn-secondary py-1 px-3 text-xs"
          onClick={onCancel}
        >
          Отмена
        </button>
        <span className="ml-auto text-[11px] text-gray-400">Ctrl+Enter — сохранить · Esc — отмена</span>
      </div>
    </div>
  );
}
