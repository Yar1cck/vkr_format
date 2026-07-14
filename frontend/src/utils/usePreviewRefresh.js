import { useCallback, useEffect, useRef, useState } from 'react';
import api from '../api/client';

const MAX_ATTEMPTS = 24;

const nextDelayMs = (attempt) => {
  if (attempt < 4) return 1000;
  if (attempt < 10) return 2000;
  return 3000;
};

// Финализация TOC + регенерация превью идут в ФОНЕ (мгновенный отклик на
// правку, ~8–15 с на рендеры). Не угадываем таймером, а опрашиваем
// report/meta: как только processed_pdf_storage_path сменился (фон дорисовал
// новый PDF) — обновляем превью ровно один раз.
//
// Возвращает [pdfVersion, bustPreview]. pdfVersion подставляется в ?v= URL
// превью (и/или в key PdfPane). bustPreview() зовётся после каждой правки.
export default function usePreviewRefresh(docId) {
  const [pdfVersion, setPdfVersion] = useState(0);
  const tokenRef = useRef(0);

  // Останавливаем опрос при размонтировании.
  useEffect(() => () => { tokenRef.current += 1; }, []);

  const bustPreview = useCallback(() => {
    setPdfVersion((n) => n + 1); // на случай быстрой/синхронной регенерации
    if (!docId) return;
    const token = ++tokenRef.current;
    let baseline;
    const tick = async (attempt) => {
      if (token !== tokenRef.current) return; // новая правка/размонтирование
      try {
        const { data } = await api.get(`/documents/${docId}/report/meta`);
        const path = data?.processed_pdf_storage_path ?? null;
        if (baseline === undefined) {
          baseline = path; // фон ещё не готов — это «старый» путь
        } else if (path && path !== baseline) {
          if (token === tokenRef.current) setPdfVersion((n) => n + 1);
          return; // фон дорисовал — обновили и вышли
        }
      } catch {
        /* меты ещё нет / сетевой сбой — повторим */
      }
      if (attempt < MAX_ATTEMPTS) {
        window.setTimeout(() => tick(attempt + 1), nextDelayMs(attempt));
      }
    };
    window.setTimeout(() => tick(0), 400);
  }, [docId]);

  return [pdfVersion, bustPreview];
}
