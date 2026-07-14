import axios from 'axios';

// 5 минут — компромисс между «достаточно для upload 50MB на медленной сети»
// и «не висим бесконечно, когда бэкенд упал». Длинные операции (preview-
// генерация, обработка pipeline) на стороне сервера занимают <60с, апвоулд
// — основной потенциальный долгожитель.
const REQUEST_TIMEOUT_MS = 5 * 60 * 1000;

// Retry только идемпотентных GET-запросов: POST/PUT/PATCH могут быть
// не-idempotent (например, апдейт нарушения с side-effect-каскадом),
// и повтор может задвоить операцию.
const RETRY_METHODS = new Set(['get']);
const MAX_RETRIES = 2;

const RETRYABLE_STATUS = (status) => status === 0 || status >= 500;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost/api/v1',
  timeout: REQUEST_TIMEOUT_MS
});

const clearStoredTokens = () => {
  sessionStorage.removeItem('access_token');
  sessionStorage.removeItem('refresh_token');
};

api.interceptors.request.use((config) => {
  const token = sessionStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const status = error?.response?.status;
    const hasToken = Boolean(sessionStorage.getItem('access_token'));

    if (status === 401 && hasToken) {
      clearStoredTokens();
      if (typeof window !== 'undefined') {
        window.location.reload();
      }
      return Promise.reject(error);
    }

    // Retry на сетевых ошибках и 5xx — только для GET. На 408/429 не
    // повторяем: 429 — это сигнал rate-limiter, и повтор только усугубит.
    const config = error?.config;
    const method = (config?.method || '').toLowerCase();
    const isRetryable =
      config &&
      RETRY_METHODS.has(method) &&
      (error?.code === 'ECONNABORTED' || // axios timeout
        !error.response ||                 // network error
        RETRYABLE_STATUS(status));

    if (isRetryable) {
      config.__retryCount = (config.__retryCount || 0) + 1;
      if (config.__retryCount <= MAX_RETRIES) {
        // 500ms → 1000ms экспоненциальный backoff с лёгким jitter, чтобы
        // не синхронизировать всплески ретраев у разных клиентов.
        const delay = 500 * Math.pow(2, config.__retryCount - 1) + Math.random() * 100;
        await sleep(delay);
        return api(config);
      }
    }

    return Promise.reject(error);
  }
);

export default api;
