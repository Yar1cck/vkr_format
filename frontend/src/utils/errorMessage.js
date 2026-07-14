export default function getApiErrorMessage(error, fallback = 'Ошибка запроса') {
  const detail = error?.response?.data?.detail;

  if (!detail) {
    return fallback;
  }

  if (typeof detail === 'string') {
    return detail;
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === 'string') {
          return item;
        }
        if (item && typeof item === 'object') {
          return item.msg || item.message || JSON.stringify(item);
        }
        return null;
      })
      .filter(Boolean);

    if (messages.length > 0) {
      return messages.join('; ');
    }
  }

  if (typeof detail === 'object') {
    return detail.message || JSON.stringify(detail);
  }

  return fallback;
}
