import React, { useEffect, useRef, useState } from 'react';
import * as pdfjsLib from 'pdfjs-dist';
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import 'pdfjs-dist/web/pdf_viewer.css';
import '../styles/pdf-pane.css';

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

const RENDER_SCALE = 1.35;

// Сворачивает все пробельные символы (пробелы, табы, NBSP, переносы строк)
// в один ASCII-пробел и приводит к нижнему регистру. В текстовом слое PDF
// иногда встречаются soft-wrap-разрывы внутри слов или другие пробельные
// символы, чем в исходном docx — буквальный .indexOf тогда не матчит;
// нормализованное представление сглаживает эти расхождения.
function normaliseChar(ch) {
  if (/[\s\u00a0\u202f\u2007]/.test(ch)) return ' ';
  return ch.toLowerCase();
}

function buildPageTextIndex(textContent) {
  // Уплощаем textContent.items в нормализованную строку и для каждого
  // символа храним обратное отображение { itemIndex, offsetInItem } —
  // тогда совпадения в нормализованном представлении можно отобразить
  // обратно в text-span'ы pdf.js.
  let fullText = '';
  const offsets = [];          // на item: { itemIndex, start, end }
  const charMap = [];          // на символ: { itemIndex, offsetInItem }
  const lineBreaks = [];       // оффсеты в fullText, разделяющие визуальные строки
  textContent.items.forEach((item, i) => {
    if (typeof item.str !== 'string') return;
    const itemStart = fullText.length;
    for (let k = 0; k < item.str.length; k++) {
      const ch = normaliseChar(item.str[k]);
      // Сворачиваем подряд идущие пробелы в нормализованном виде.
      if (ch === ' ' && fullText.endsWith(' ')) {
        continue;
      }
      fullText += ch;
      charMap.push({ itemIndex: i, offsetInItem: k });
    }
    offsets.push({ itemIndex: i, start: itemStart, end: fullText.length });
    if (item.hasEOL && !fullText.endsWith(' ')) {
      lineBreaks.push(fullText.length); // позиция разрыва строки
      fullText += ' ';
      charMap.push({ itemIndex: i, offsetInItem: item.str.length });
    }
  });
  return { fullText, offsets, charMap, lineBreaks };
}

// Является ли символ «словесным» (буква/цифра любой письменности). Нужен,
// чтобы не подсвечивать иголку, застрявшую в середине другого слова.
function isWordChar(ch) {
  return !!ch && /[\p{L}\p{N}]/u.test(ch);
}

// Границы визуальной строки [start, end), внутри которой лежит pos.
function lineRange(index, pos) {
  let start = 0;
  let end = index.fullText.length;
  for (const b of index.lineBreaks) {
    if (b <= pos) start = b + 1;
    else { end = b; break; }
  }
  return [start, end];
}

// «Заголовко-подобная» иголка: только буквы/пробелы/типографика, без цифр и
// скобок. Для таких (СОДЕРЖАНИЕ, Введение) требуем, чтобы совпадение было
// почти целой строкой — иначе это просто слово в середине абзаца (ложное
// подчёркивание). Цитаты «[3-5]», формулы и подписи с цифрами под это
// правило не попадают и матчатся как раньше.
function isTitleLike(s) {
  const t = s.trim();
  return t.length >= 4 && /^[\p{L}][\p{L}\s.,:'’«»()-]*$/u.test(t) && !/\d/.test(t);
}

// Все вхождения подстроки.
function allOccurrences(hay, needle) {
  const res = [];
  let from = 0;
  let p;
  while ((p = hay.indexOf(needle, from)) !== -1) {
    res.push(p);
    from = p + 1;
  }
  return res;
}

// Лучшее вхождение titleLike-иголки: максимально доминирующее свою строку и
// стоящее на границах слова. Возвращает оффсет или -1, если надёжного якоря
// нет (тогда лучше не подсвечивать ничего, чем подсветить чужое слово).
function bestTitleOccurrence(index, norm) {
  let best = -1;
  let bestScore = -1;
  for (const p of allOccurrences(index.fullText, norm)) {
    const [ls, le] = lineRange(index, p);
    const lineLen = Math.max(le - ls, norm.length);
    const dominance = norm.length / lineLen; // 1.0 ⇒ иголка = вся строка
    const before = p > ls ? index.fullText[p - 1] : ' ';
    const after = p + norm.length < le ? index.fullText[p + norm.length] : ' ';
    const wordBounded = !isWordChar(before) && !isWordChar(after);
    const score = dominance + (wordBounded ? 0.25 : 0);
    if (score > bestScore) { bestScore = score; best = p; }
  }
  return bestScore >= 0.6 ? best : -1;
}

function normaliseNeedle(s) {
  return s.replace(/[\s\u00a0\u202f\u2007]+/g, ' ').trim().toLowerCase();
}

// \u041f\u043e\u0445\u043e\u0436\u0435 \u043b\u0438 \u0441\u043e\u0434\u0435\u0440\u0436\u0438\u043c\u043e\u0435 \u0441\u0442\u0440\u0430\u043d\u0438\u0446\u044b \u043d\u0430 \u0441\u0433\u0435\u043d\u0435\u0440\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u043e\u0435 \u043e\u0433\u043b\u0430\u0432\u043b\u0435\u043d\u0438\u0435. \u0412 \u0438\u0441\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043d\u043e\u043c
// \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0435 \u0421\u041e\u0414\u0415\u0420\u0416\u0410\u041d\u0418\u0415 \u0441\u043e\u0434\u0435\u0440\u0436\u0438\u0442 \u0442\u0435\u043a\u0441\u0442 \u041a\u0410\u0416\u0414\u041e\u0413\u041e \u0437\u0430\u0433\u043e\u043b\u043e\u0432\u043a\u0430, \u043f\u043e\u044d\u0442\u043e\u043c\u0443 \u043f\u0435\u0440\u0432\u043e\u0435
// \u0441\u043e\u0432\u043f\u0430\u0434\u0435\u043d\u0438\u0435 needl-\u0430 (\u0438 \u0430\u0432\u0442\u043e\u0441\u043a\u0440\u043e\u043b\u043b) \u043f\u043e\u043f\u0430\u0434\u0430\u043b\u043e \u0432 \u0441\u0442\u0440\u043e\u043a\u0443 TOC, \u0430 \u043d\u0435 \u0432 \u0440\u0435\u0430\u043b\u044c\u043d\u044b\u0439
// \u0430\u0431\u0437\u0430\u0446 \u0442\u0435\u043b\u0430. \u041f\u043e\u043c\u0435\u0447\u0430\u0435\u043c \u0442\u0430\u043a\u0438\u0435 \u0441\u0442\u0440\u0430\u043d\u0438\u0446\u044b \u0438 \u043f\u0440\u043e\u043f\u0443\u0441\u043a\u0430\u0435\u043c \u0438\u0445 \u043f\u0440\u0438 \u043f\u043e\u0434\u0441\u0432\u0435\u0442\u043a\u0435.
function pageLooksLikeToc(textContent) {
  const lines = [];
  let line = '';
  for (const it of textContent.items) {
    if (typeof it.str === 'string') line += it.str;
    if (it.hasEOL) { lines.push(line); line = ''; }
  }
  if (line) lines.push(line);
  let head = false;
  let leader = 0;
  for (const ln of lines) {
    const t = ln.trim().toLowerCase();
    if (!t) continue;
    if (t === '\u0441\u043e\u0434\u0435\u0440\u0436\u0430\u043d\u0438\u0435' || t === '\u043e\u0433\u043b\u0430\u0432\u043b\u0435\u043d\u0438\u0435') head = true;
    // \u0441\u0442\u0440\u043e\u043a\u0430-\u0437\u0430\u043f\u0438\u0441\u044c TOC: \u00ab\u2026 . . . . 12\u00bb (\u0442\u043e\u0447\u0435\u0447\u043d\u044b\u0439 \u043b\u0438\u0434\u0435\u0440 + \u043d\u043e\u043c\u0435\u0440 \u0441\u0442\u0440\u0430\u043d\u0438\u0446\u044b)
    if (/[.\u2026]{3,}\s*\d{1,4}$/.test(t)) leader++;
  }
  return head || leader >= 4;
}

function findMatches(index, needles) {
  // Возвращает [{ start, end, needle }] — первое вхождение каждого needle.
  // Если точного совпадения нет, откатывается к укороченному префиксу
  // (например, заголовок изменился между записью нарушения и рендером PDF).
  const matches = [];
  for (const n of needles) {
    if (!n) continue;
    const normalised = normaliseNeedle(n);
    if (normalised.length < 3) continue;
    // Заголовко-подобные иголки якорим строго: совпадение должно быть почти
    // целой строкой. Это убирает ложные подчёркивания, когда короткое слово
    // ("содержание", "введение") встречается в середине обычного абзаца.
    if (isTitleLike(n)) {
      const at = bestTitleOccurrence(index, normalised);
      if (at !== -1) {
        matches.push({ start: at, end: at + normalised.length, needle: n });
      }
      continue;
    }
    let idx = index.fullText.indexOf(normalised);
    let matchLen = normalised.length;
    if (idx === -1 && normalised.length > 20) {
      // Пробуем всё более короткие префиксы — покрывает перенумерацию
      // подписей, удаление слова-главы, дрейф пробелов.
      for (const cut of [40, 30, 20]) {
        if (normalised.length <= cut) continue;
        const prefix = normalised.slice(0, cut);
        const found = index.fullText.indexOf(prefix);
        if (found !== -1) { idx = found; matchLen = cut; break; }
      }
    }
    if (idx !== -1) matches.push({ start: idx, end: idx + matchLen, needle: n });
  }
  return matches;
}

function markSpansForMatch(index, match, spans) {
  // Помечает каждый span в textLayer, чей текстовый item пересекается с
  // диапазоном совпадения.
  for (const off of index.offsets) {
    if (off.end <= match.start) continue;
    if (off.start >= match.end) break;
    const span = spans[off.itemIndex];
    if (span) span.dataset.vkrMatch = '1';
  }
}

function applyHighlights(pageEls, highlights, activeText, onHighlightClick) {
  // highlights: string[], activeText: string | null
  const needles = Array.from(new Set([...(highlights ?? []), ...(activeText ? [activeText] : [])].filter(Boolean)));

  let firstActiveSpan = null;
  // Запасной элемент для скролла: страница-плейсхолдер, у которой есть
  // текстовый индекс (предзагружен), но ещё нет отрендеренного text-layer.
  // scrollIntoView на ней прокрутит к нужной странице; IO-наблюдатель
  // затем дорендерит canvas+text-layer и нанесёт подсветку.
  let firstActivePageEl = null;

  // Найдено ли совпадение needl-а вне региона оглавления. Берём ВСЕ страницы
  // из контейнера (индексы предзагружены), а не только переданный pageEls —
  // вызов из IO-наблюдателя приходит для одной страницы.
  const allPages = pageEls.length
    ? Array.from(
        pageEls[0].parentNode?.querySelectorAll('.vkr-pdf-page') ?? pageEls,
      )
    : [];
  const indexHasNeedle = (index, n) => {
    const norm = normaliseNeedle(n);
    if (norm.length < 3) return false;
    if (isTitleLike(n)) return bestTitleOccurrence(index, norm) !== -1;
    if (index.fullText.indexOf(norm) !== -1) return true;
    if (norm.length > 20) {
      for (const cut of [40, 30, 20]) {
        if (norm.length <= cut) continue;
        if (index.fullText.indexOf(norm.slice(0, cut)) !== -1) return true;
      }
    }
    return false;
  };
  const bodyMatch = new Set();
  for (const n of needles) {
    for (const pe of allPages) {
      if (pe.__vkrIsToc) continue;
      if (pe.__vkrIndex && indexHasNeedle(pe.__vkrIndex, n)) {
        bodyMatch.add(n);
        break;
      }
    }
  }
  // Пропускать ли needle на странице оглавления: да, если он есть в теле
  // (тогда подсвечиваем реальный абзац). Если в теле его нет (короткий док —
  // заголовок только в TOC) — НЕ пропускаем, иначе ничего не подсветится.
  const skipOnToc = (pageEl, n) => pageEl.__vkrIsToc && bodyMatch.has(n);

  for (const pageEl of pageEls) {
    const textLayer = pageEl.querySelector('.vkr-pdf-text-layer');
    const index = pageEl.__vkrIndex;
    if (!index) continue;

    if (!textLayer) {
      // Страница ещё не отрендерена. Если activeText есть в предзагруженном
      // индексе — запоминаем страницу-плейсхолдер как цель скролла.
      if (
        activeText && !firstActiveSpan && !firstActivePageEl &&
        !skipOnToc(pageEl, activeText)
      ) {
        const norm = normaliseNeedle(activeText);
        const present = norm.length >= 3 && (
          isTitleLike(activeText)
            ? bestTitleOccurrence(index, norm) !== -1
            : index.fullText.indexOf(norm) !== -1
        );
        if (present) {
          firstActivePageEl = pageEl;
        }
      }
      continue;
    }

    // Очищаем предыдущие маркеры
    textLayer.querySelectorAll('[data-vkr-match], [data-vkr-active]').forEach((el) => {
      el.removeAttribute('data-vkr-match');
      el.removeAttribute('data-vkr-active');
    });

    const spans = Array.from(textLayer.children);

    // Проход 1 — все подсветки (жёлтым)
    for (const n of needles) {
      if (!n || n === activeText) continue;
      if (skipOnToc(pageEl, n)) continue;
      const matches = findMatches(index, [n]);
      for (const m of matches) {
        markSpansForMatch(index, m, spans);
        for (const off of index.offsets) {
          if (off.end <= m.start) continue;
          if (off.start >= m.end) break;
          const span = spans[off.itemIndex];
          if (span) span.dataset.vkrNeedle = n;
        }
      }
    }

    // Проход 2 — активный текст (красным) поверх всего
    if (activeText && !skipOnToc(pageEl, activeText)) {
      const activeMatches = findMatches(index, [activeText]);
      for (const m of activeMatches) {
        for (const off of index.offsets) {
          if (off.end <= m.start) continue;
          if (off.start >= m.end) break;
          const span = spans[off.itemIndex];
          if (span) {
            span.dataset.vkrActive = '1';
            if (!firstActiveSpan) firstActiveSpan = span;
          }
        }
      }
    }
  }

  // Навешиваем по одному делегированному click-обработчику на text-layer
  // каждой страницы — клик по подсвеченному span выбирает соответствующее
  // нарушение в боковой панели (двусторонний выбор). Прежний обработчик
  // заменяется.
  if (onHighlightClick) {
    for (const pageEl of pageEls) {
      const textLayer = pageEl.querySelector('.vkr-pdf-text-layer');
      if (!textLayer) continue;
      if (textLayer.__vkrClickHandler) {
        textLayer.removeEventListener('click', textLayer.__vkrClickHandler);
      }
      const handler = (e) => {
        const span = e.target.closest('[data-vkr-needle]');
        if (!span) return;
        onHighlightClick(span.dataset.vkrNeedle);
      };
      textLayer.addEventListener('click', handler);
      textLayer.__vkrClickHandler = handler;
    }
  }

  return firstActiveSpan ?? firstActivePageEl;
}

// F-02 — lazy rendering. Раньше все страницы (canvas + text-layer) грузились
// сразу: для 80-страничного документа это ~40 МБ canvas в DOM и 10–20 секунд
// на загрузку, причём пользователь видит только 1–2 страницы за раз.
// Сейчас: на старте создаём только placeholder'ы с правильным размером,
// каждый помечен номером страницы. Реальный рендер canvas + text-layer
// происходит ленивo через IntersectionObserver, когда placeholder попадает
// в видимую область (с запасом 800px сверху/снизу — рендер успевает до того,
// как пользователь долистает).
function renderPagePlaceholder(container, page, pageNum) {
  const viewport = page.getViewport({ scale: RENDER_SCALE });

  const pageEl = document.createElement('div');
  pageEl.className = 'vkr-pdf-page';
  pageEl.style.width = `${viewport.width}px`;
  pageEl.style.height = `${viewport.height}px`;
  pageEl.dataset.pageNum = String(pageNum);
  // Сохраняем страничные параметры на DOM-узле — пригодится при ленивом
  // рендере. `__vkrPage` — само Page-API pdf.js, viewport — заранее
  // посчитанный, чтобы не вызывать getViewport второй раз.
  pageEl.__vkrPage = page;
  pageEl.__vkrViewport = viewport;
  pageEl.__vkrRendered = false;

  const labelEl = document.createElement('div');
  labelEl.className = 'vkr-pdf-page-label';
  labelEl.textContent = `Стр. ${pageNum}`;

  container.appendChild(pageEl);
  container.appendChild(labelEl);
  return pageEl;
}

async function renderPageContent(pageEl) {
  if (pageEl.__vkrRendered) return;
  // Помечаем сразу — рендер async, второй observer-callback не должен
  // запустить рендер параллельно для той же страницы.
  pageEl.__vkrRendered = true;

  const page = pageEl.__vkrPage;
  const viewport = pageEl.__vkrViewport;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);

  const canvas = document.createElement('canvas');
  canvas.width = Math.floor(viewport.width * dpr);
  canvas.height = Math.floor(viewport.height * dpr);
  canvas.style.width = `${viewport.width}px`;
  canvas.style.height = `${viewport.height}px`;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  pageEl.appendChild(canvas);

  const textLayerDiv = document.createElement('div');
  textLayerDiv.className = 'vkr-pdf-text-layer textLayer';
  textLayerDiv.style.setProperty('--scale-factor', String(RENDER_SCALE));
  textLayerDiv.style.width = `${viewport.width}px`;
  textLayerDiv.style.height = `${viewport.height}px`;
  pageEl.appendChild(textLayerDiv);

  await page.render({ canvasContext: ctx, viewport }).promise;

  const textContent = await page.getTextContent();
  const tl = new pdfjsLib.TextLayer({ textContentSource: textContent, container: textLayerDiv, viewport });
  await tl.render();

  pageEl.__vkrIndex = buildPageTextIndex(textContent);
  pageEl.__vkrIsToc = pageLooksLikeToc(textContent);
}

export default function PdfPane({ url, label, highlights = [], activeText = null, onHighlightClick, refreshing = false }) {
  const containerRef = useRef(null);
  const viewportRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [ready, setReady] = useState(false);
  // Масштаб задаётся CSS-свойством zoom: визуально увеличивает уже
  // отрисованный canvas без перегенерации страниц. Достаточно для просмотра;
  // если нужен идеально чёткий рендер, можно добавить пере-рендер виртуально
  // позже. Шаг — 10%, диапазон 50%..300%.
  const [zoom, setZoom] = useState(0.8);

  // Отслеживаем activeText, на который последний раз был auto-scroll, и
  // прокручивал ли пользователь колесом с тех пор. Как только пользователь
  // прокрутил колёсиком, мы перестаём дёргать вид обратно к активной
  // подсветке — пока не придёт *новый* activeText (новый клик в сайдбаре).
  const lastScrolledActiveRef = useRef(null);
  const userScrolledRef = useRef(false);
  const firstActiveSpanRef = useRef(null);

  // Текущие highlights/activeText храним в ref'ах, чтобы IntersectionObserver
  // мог переприменить подсветку к страницам, которые рендерятся лениво —
  // useEffect для applyHighlights отрабатывает только на маунте/смене props,
  // а ленивый рендер случается уже после.
  const highlightsRef = useRef(highlights);
  const activeTextRef = useRef(activeText);
  const onHighlightClickRef = useRef(onHighlightClick);
  highlightsRef.current = highlights;
  activeTextRef.current = activeText;
  onHighlightClickRef.current = onHighlightClick;

  useEffect(() => {
    let cancelled = false;
    let observer = null;
    setLoading(true);
    setError(null);
    setReady(false);
    if (containerRef.current) containerRef.current.innerHTML = '';

    const token = sessionStorage.getItem('access_token');
    const loadingTask = pdfjsLib.getDocument({
      url,
      httpHeaders: token ? { Authorization: `Bearer ${token}` } : {},
      withCredentials: false,
    });

    (async () => {
      try {
        const pdf = await loadingTask.promise;
        if (cancelled) return;
        // Сначала плейсхолдеры — быстрая операция (только getPage + viewport).
        const pageEls = [];
        for (let i = 1; i <= pdf.numPages; i++) {
          if (cancelled) return;
          const page = await pdf.getPage(i);
          if (cancelled) return;
          pageEls.push(renderPagePlaceholder(containerRef.current, page, i));
        }
        if (cancelled) return;

        // Lazy-рендер canvas+text-layer через IntersectionObserver.
        // rootMargin=800px — рендерим страницы заранее на ~2 экрана вперёд,
        // чтобы пользователь не упёрся в пустой placeholder при быстром
        // скролле колесом. root=null значит «относительно viewport».
        observer = new IntersectionObserver(
          (entries) => {
            for (const entry of entries) {
              if (!entry.isIntersecting) continue;
              const pageEl = entry.target;
              if (pageEl.__vkrRendered) {
                observer.unobserve(pageEl);
                continue;
              }
              renderPageContent(pageEl).then(() => {
                if (cancelled) return;
                // После ленивого рендера переприменяем подсветку к этой
                // конкретной странице — чтобы при скролле к новой странице
                // активные/обычные подсветки сразу появлялись.
                applyHighlights(
                  [pageEl],
                  highlightsRef.current ?? [],
                  activeTextRef.current ?? null,
                  onHighlightClickRef.current,
                );
              }).catch(() => {
                // Сбой рендера одной страницы не должен ломать остальные —
                // pdf.js может выбросить при destroy()'нутом loadingTask.
              });
              observer.unobserve(pageEl);
            }
          },
          { root: null, rootMargin: '800px 0px', threshold: 0 },
        );
        for (const pageEl of pageEls) observer.observe(pageEl);

        if (!cancelled) { setLoading(false); setReady(true); }

        // Фоново предзагружаем текстовые индексы всех страниц (только
        // getTextContent — без canvas, дёшево). Это позволяет findMatches
        // искать текст на любой странице до того, как IO-наблюдатель
        // дорендерит её canvas+text-layer, и возвращать страницу-плейсхолдер
        // как цель scrollIntoView при клике на нарушение.
        ;(async () => {
          for (const pageEl of pageEls) {
            if (cancelled) return;
            if (pageEl.__vkrIndex) continue; // IO уже успел отрендерить
            try {
              const tc = await pageEl.__vkrPage.getTextContent();
              if (!pageEl.__vkrIndex) {
                pageEl.__vkrIndex = buildPageTextIndex(tc);
                pageEl.__vkrIsToc = pageLooksLikeToc(tc);
              }
            } catch (_) {}
          }
        })();
      } catch (e) {
        if (!cancelled) { setError(String(e)); setLoading(false); }
      }
    })();

    return () => {
      cancelled = true;
      if (observer) observer.disconnect();
      loadingTask.destroy?.();
    };
  }, [url]);

  useEffect(() => {
    if (!ready || !containerRef.current) return;
    const pages = containerRef.current.querySelectorAll('.vkr-pdf-page');
    const firstActive = applyHighlights(pages, highlights, activeText, onHighlightClick);
    firstActiveSpanRef.current = firstActive;

    // Auto-scroll делаем только когда activeText сменился на новое значение
    // и пользователь не прокручивал вручную с прошлого auto-scroll'а.
    if (activeText && activeText !== lastScrolledActiveRef.current) {
      userScrolledRef.current = false;
      lastScrolledActiveRef.current = activeText;
      if (firstActive && viewportRef.current) {
        const vp = viewportRef.current;
        const vpRect = vp.getBoundingClientRect();
        const elRect = firstActive.getBoundingClientRect();
        // Скроллим только PDF-контейнер, не весь браузер (scrollIntoView
        // трогает всех прокручиваемых предков). getBoundingClientRect и
        // scrollBy работают в одних CSS-пикселях (zoom уже учтён в обоих),
        // поэтому деление на zoom не нужно.
        const isPage = firstActive.classList.contains('vkr-pdf-page');
        // Для плейсхолдера-страницы — выравниваем верх с небольшим отступом,
        // для конкретного span — центрируем в видимой области.
        const targetOffset = isPage
          ? 32
          : (vpRect.height - elRect.height) / 2;
        const delta = elRect.top - vpRect.top - targetOffset;
        vp.scrollBy({ top: delta, behavior: 'smooth' });
      }
    } else if (!activeText) {
      lastScrolledActiveRef.current = null;
    }
  }, [ready, highlights, activeText, onHighlightClick]);

  useEffect(() => {
    const vp = viewportRef.current;
    if (!vp) return;
    const onWheel = () => { userScrolledRef.current = true; };
    vp.addEventListener('wheel', onWheel, { passive: true });
    return () => vp.removeEventListener('wheel', onWheel);
  }, []);

  const zoomIn   = () => setZoom((z) => Math.min(3, +(z + 0.1).toFixed(2)));
  const zoomOut  = () => setZoom((z) => Math.max(0.5, +(z - 0.1).toFixed(2)));
  const zoomReset = () => setZoom(0.8);

  return (
    <div className="flex flex-col h-full">
      {(label || !error) && (
        <div className="shrink-0 flex items-center gap-2 px-3 py-1 text-xs font-medium text-gray-500 bg-gray-50 border-b">
          <span className="flex-1 text-center truncate">{label}</span>
          {!error && (
            <div className="flex items-center gap-0.5 shrink-0">
              <button
                type="button"
                onClick={zoomOut}
                disabled={zoom <= 0.5}
                title="Уменьшить (10%)"
                className="px-2 py-0.5 rounded hover:bg-gray-200 disabled:opacity-40 text-base leading-none"
              >−</button>
              <button
                type="button"
                onClick={zoomReset}
                title="Сбросить масштаб"
                className="px-1.5 py-0.5 rounded hover:bg-gray-200 text-[11px] tabular-nums w-12 text-center"
              >{Math.round(zoom * 100)}%</button>
              <button
                type="button"
                onClick={zoomIn}
                disabled={zoom >= 3}
                title="Увеличить (10%)"
                className="px-2 py-0.5 rounded hover:bg-gray-200 disabled:opacity-40 text-base leading-none"
              >+</button>
            </div>
          )}
        </div>
      )}
      {error ? (
        <div className="flex-1 flex items-center justify-center text-sm text-gray-400 text-center p-6">
          Превью недоступен
        </div>
      ) : (
        <div ref={viewportRef} className="flex-1 overflow-auto relative vkr-pdf-viewport">
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center text-sm text-gray-400 bg-gray-50 z-10">
              Загрузка превью…
            </div>
          )}
          {!loading && refreshing && (
            <div className="absolute top-2 right-2 z-10 pointer-events-none">
              <span className="text-xs text-gray-500 bg-white border border-gray-200 rounded px-2 py-1 shadow-sm opacity-90">
                Обновление…
              </span>
            </div>
          )}
          <div ref={containerRef} className="vkr-pdf-scroll" style={{ zoom }} />
        </div>
      )}
    </div>
  );
}
