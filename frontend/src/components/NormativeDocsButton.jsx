import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

export default function NormativeDocsButton() {
  const [open, setOpen] = useState(false);
  const [rect, setRect] = useState(null);
  const [docs, setDocs] = useState(null);
  const btnRef = useRef(null);
  // Панель рендерится через createPortal в document.body — она НЕ является
  // DOM-потомком btnRef. Без отдельного ref клик по ссылке внутри панели
  // ловился как «клик снаружи»: mousedown закрывал панель (unmount ссылки)
  // раньше, чем браузер успевал перейти по href — ссылки просто исчезали.
  const panelRef = useRef(null);

  useEffect(() => {
    fetch('/api/v1/normative/reference-docs')
      .then((r) => r.ok ? r.json() : [])
      .then(setDocs)
      .catch(() => setDocs([]));
  }, []);

  useEffect(() => {
    if (!open) return;
    const close = (e) => {
      if (btnRef.current?.contains(e.target)) return;
      if (panelRef.current?.contains(e.target)) return;
      setOpen(false);
    };
    const esc = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', esc);
    };
  }, [open]);

  const toggle = () => {
    const r = btnRef.current?.getBoundingClientRect();
    setRect(r ?? null);
    setOpen((v) => !v);
  };

  return (
    <div className="relative inline-block">
      <button
        ref={btnRef}
        onClick={toggle}
        className="text-xs text-gray-500 hover:text-gray-700 transition-colors flex items-center gap-1"
        title="Нормативная база"
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
        Нормативная база
      </button>

      {open && rect && createPortal(
        <div
          ref={panelRef}
          style={{ position: 'fixed', top: rect.bottom + 4, right: window.innerWidth - rect.right, zIndex: 9999 }}
          className="w-72 bg-white dark:bg-[#242424] border border-gray-200 dark:border-[#3a3a3a] rounded-xl shadow-panel py-1"
        >
          {docs === null && (
            <p className="px-4 py-2 text-xs text-gray-400">Загрузка…</p>
          )}
          {docs !== null && docs.length === 0 && (
            <p className="px-4 py-2 text-xs text-gray-400">Документы недоступны</p>
          )}
          {docs !== null && docs.map((doc) => (
            <a
              key={doc.slug}
              href={doc.url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
            >
              <svg className="w-4 h-4 text-red-500 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 6a1 1 0 011-1h6a1 1 0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z" clipRule="evenodd" />
              </svg>
              <span className="leading-tight">{doc.name}</span>
            </a>
          ))}
        </div>,
        document.body
      )}
    </div>
  );
}
