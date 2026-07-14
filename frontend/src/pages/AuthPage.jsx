import React, { useState } from 'react';

import api from '../api/client';
import useAuthStore from '../store/auth';
import getApiErrorMessage from '../utils/errorMessage';

function AuthPage() {
  const { setTokens } = useAuthStore();
  const [mode, setMode] = useState('login');
  const [form, setForm] = useState({
    email: '',
    full_name: '',
    password: '',
  });
  const [error, setError] = useState('');

  const submit = async (event) => {
    event.preventDefault();
    setError('');
    try {
      if (mode === 'register') {
        await api.post('/auth/register', {
          email: form.email,
          full_name: form.full_name,
          password: form.password,
        });
      }
      const response = await api.post('/auth/login', {
        email: form.email,
        password: form.password
      });
      setTokens(response.data.access_token, response.data.refresh_token);
    } catch (e) {
      setError(getApiErrorMessage(e, 'Ошибка авторизации'));
    }
  };

  return (
    <div className="relative min-h-screen flex flex-col items-center justify-center px-4">

      {/* Карточка входа */}
      <div className="relative z-10 w-full max-w-md">
        {/* Логотип / заголовок */}
        <div className="mb-6 text-center">
          <div className="inline-flex items-center gap-2 mb-3">
            <div className="w-9 h-9 rounded-lg bg-brand-600 flex items-center justify-center">
              <span className="text-white text-xs font-extrabold tracking-tight">ВКР</span>
            </div>
            <span className="text-xl font-bold text-gray-900">
              ВКР<span className="text-brand-600">.Формат</span>
            </span>
          </div>
          <p className="text-sm text-slate-500">
            Оформление выпускной квалификационной работы<br/>по требованиям МИИГАиК
          </p>
        </div>

        <div className="card shadow-lg">
          <h2 className="mb-5 text-lg font-semibold text-gray-900">
            {mode === 'login' ? 'Вход в систему' : 'Регистрация'}
          </h2>

          <form className="space-y-3" onSubmit={submit}>
            <input
              className="input"
              placeholder="Email"
              type="email"
              value={form.email}
              onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
            />

            {mode === 'register' && (
              <>
                <input
                  className="input"
                  placeholder="ФИО"
                  value={form.full_name}
                  onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))}
                />
                <p className="text-xs text-slate-500">
                  Регистрация создаёт аккаунт студента. Роли руководителя,
                  декана и администратора назначаются администратором сервиса.
                </p>
              </>
            )}

            <input
              className="input"
              placeholder="Пароль"
              type="password"
              value={form.password}
              onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
            />

            {error && (
              <div className="rounded-xl bg-danger-50 p-3 text-sm text-danger-600">{error}</div>
            )}

            <button className="btn-primary w-full py-2.5" type="submit">
              {mode === 'login' ? 'Войти' : 'Создать аккаунт'}
            </button>
          </form>

          <button
            className="mt-4 w-full text-sm text-brand-600 hover:text-brand-700"
            onClick={() => setMode(mode === 'login' ? 'register' : 'login')}
          >
            {mode === 'login' ? 'Нет аккаунта? Регистрация →' : '← Уже есть аккаунт? Войти'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default AuthPage;
