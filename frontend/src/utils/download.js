// Скачивание файлов из API + парсинг content-disposition.
// Раньше эта логика жила в StudentPage и StaffPage отдельными копиями.

import api from '../api/client';

// Извлекает имя файла из заголовка Content-Disposition.
// Поддерживает оба варианта: RFC 5987 (filename*=UTF-8''…) и старый
// ASCII filename=. Если ничего не пришло — возвращает fallback.
export function parseFilename(headers, fallback) {
  const disp = headers?.['content-disposition'];
  if (!disp) return fallback;
  const utf = disp.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf?.[1]) {
    try { return decodeURIComponent(utf[1]); } catch { return utf[1]; }
  }
  const ascii = disp.match(/filename="?([^";]+)"?/i);
  return ascii?.[1] ?? fallback;
}

// Сохраняет blob под именем name через временный <a download>.
// URL.createObjectURL ОБЯЗАТЕЛЬНО освобождаем — иначе утечка памяти
// при последовательных скачиваниях.
export function downloadBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// Скачивание файла из API. Использует axios c responseType=blob, чтобы
// токен ушёл в Authorization-заголовке (через <a href> токены не уходят
// — браузер их не подставляет).
// onError вызывается при ошибке; если не передан — показывается alert.
export async function downloadViaApi(path, filename, onError) {
  try {
    const res = await api.get(path, { responseType: 'blob' });
    const name = filename ?? parseFilename(res.headers, 'file');
    downloadBlob(res.data, name);
  } catch (err) {
    if (onError) {
      onError(err);
    } else {
      const status = err?.response?.status ?? err?.message ?? 'ошибка';
      alert(`Не удалось скачать файл: ${status}`);
    }
  }
}
