import { create } from 'zustand';

import api from '../api/client';

const decodeBase64Url = (value) => {
  try {
    const normalized = value.replace(/-/g, '+').replace(/_/g, '/');
    const padding = (4 - (normalized.length % 4)) % 4;
    const padded = normalized + '='.repeat(padding);
    return atob(padded);
  } catch {
    return null;
  }
};

const parseToken = (token) => {
  if (!token) return null;

  const parts = token.split('.');
  if (parts.length !== 3) return null;

  const decodedPayload = decodeBase64Url(parts[1]);
  if (!decodedPayload) return null;

  try {
    const payload = JSON.parse(decodedPayload);
    if (!payload?.sub || !payload?.role) return null;

    if (payload.exp && Date.now() >= payload.exp * 1000) {
      return null;
    }

    return { id: payload.sub, role: payload.role };
  } catch {
    return null;
  }
};

const clearStoredTokens = () => {
  sessionStorage.removeItem('access_token');
  sessionStorage.removeItem('refresh_token');
};

const readInitialAuthState = () => {
  const accessToken = sessionStorage.getItem('access_token');
  const refreshToken = sessionStorage.getItem('refresh_token');
  const user = parseToken(accessToken);

  if (!user) {
    clearStoredTokens();
    return { accessToken: null, refreshToken: null, user: null };
  }

  return {
    accessToken,
    refreshToken,
    user
  };
};

const initialState = readInitialAuthState();

const useAuthStore = create((set) => ({
  ...initialState,
  setTokens: (accessToken, refreshToken) => {
    const user = parseToken(accessToken);

    if (!accessToken || !refreshToken || !user) {
      clearStoredTokens();
      set({ accessToken: null, refreshToken: null, user: null });
      return;
    }

    sessionStorage.setItem('access_token', accessToken);
    sessionStorage.setItem('refresh_token', refreshToken);
    set({ accessToken, refreshToken, user });
  },
  logout: async () => {
    // Отзываем токены на бэке: jti обоих токенов попадает в Redis-blacklist,
    // и попытка использовать их повторно (например, с украденного устройства)
    // вернёт 401. Если бэк недоступен — всё равно чистим локально, иначе
    // пользователь не сможет выйти при сетевой проблеме.
    const refreshToken = sessionStorage.getItem('refresh_token');
    if (refreshToken) {
      try {
        await api.post('/auth/logout', { refresh_token: refreshToken });
      } catch {
        // best-effort — продолжаем cleanup
      }
    }
    clearStoredTokens();
    set({ accessToken: null, refreshToken: null, user: null });
  }
}));

export default useAuthStore;
