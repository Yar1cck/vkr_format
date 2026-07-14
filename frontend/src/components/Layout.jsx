import React, { useEffect, useState } from 'react';

import api from '../api/client';
import useAuthStore from '../store/auth';

const ROLE_LABELS = {
  student: 'Студент',
  supervisor: 'Научный руководитель',
  dean: 'Деканат',
  admin: 'Администратор'
};

const NAV_ICONS = {
  dashboard: (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
      <rect x="1" y="1" width="5.5" height="5.5" rx="1" stroke="currentColor" strokeWidth="1.4"/>
      <rect x="8.5" y="1" width="5.5" height="5.5" rx="1" stroke="currentColor" strokeWidth="1.4"/>
      <rect x="1" y="8.5" width="5.5" height="5.5" rx="1" stroke="currentColor" strokeWidth="1.4"/>
      <rect x="8.5" y="8.5" width="5.5" height="5.5" rx="1" stroke="currentColor" strokeWidth="1.4"/>
    </svg>
  ),
  documents: (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
      <rect x="2" y="1" width="9" height="13" rx="1.5" stroke="currentColor" strokeWidth="1.4"/>
      <path d="M9 1v3.5H13" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
      <line x1="4" y1="7" x2="11" y2="7" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
      <line x1="4" y1="9.5" x2="9" y2="9.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
    </svg>
  ),
  upload: (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
      <path d="M7.5 10V3M7.5 3L4.5 6M7.5 3L10.5 6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
      <path d="M2 11v1.5A1.5 1.5 0 003.5 14h8a1.5 1.5 0 001.5-1.5V11" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
    </svg>
  ),
  history: (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
      <circle cx="7.5" cy="7.5" r="5.5" stroke="currentColor" strokeWidth="1.4"/>
      <path d="M7.5 4.5V7.5L9.5 9" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  ),
  settings: (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
      <circle cx="7.5" cy="7.5" r="2" stroke="currentColor" strokeWidth="1.4"/>
      <path d="M7.5 1v1.5M7.5 12.5V14M1 7.5h1.5M12.5 7.5H14M2.9 2.9l1.05 1.05M11.05 11.05l1.05 1.05M2.9 12.1l1.05-1.05M11.05 3.95l1.05-1.05" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
    </svg>
  ),
  overview: (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
      <rect x="1.5" y="1.5" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.4"/>
      <rect x="8.5" y="1.5" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.4"/>
      <rect x="1.5" y="8.5" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.4"/>
      <rect x="8.5" y="8.5" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.4"/>
    </svg>
  ),
  users: (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
      <circle cx="5.5" cy="4.5" r="2.5" stroke="currentColor" strokeWidth="1.4"/>
      <path d="M1.5 13c0-2.2 1.8-4 4-4s4 1.8 4 4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
      <path d="M10 3.2a2.3 2.3 0 010 4.3M11.2 13c0-1.9-1.1-3.5-2.7-4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
    </svg>
  ),
  students: (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
      <circle cx="5.5" cy="4.5" r="2.5" stroke="currentColor" strokeWidth="1.4"/>
      <path d="M1.5 13c0-2.2 1.8-4 4-4s4 1.8 4 4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
      <path d="M10 3.2a2.3 2.3 0 010 4.3M11.2 13c0-1.9-1.1-3.5-2.7-4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
    </svg>
  ),
  config: (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
      <path d="M2 3.5h11M2 7.5h11M2 11.5h11" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
      <circle cx="5" cy="3.5" r="1.2" fill="white" stroke="currentColor" strokeWidth="1.2"/>
      <circle cx="9" cy="7.5" r="1.2" fill="white" stroke="currentColor" strokeWidth="1.2"/>
      <circle cx="6" cy="11.5" r="1.2" fill="white" stroke="currentColor" strokeWidth="1.2"/>
    </svg>
  ),
};

function Layout({ children, navItems = [], activeView, onNavChange }) {
  const { user, logout } = useAuthStore();
  const [profile, setProfile] = useState(null);
  const [profileLoadedFor, setProfileLoadedFor] = useState(null);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [dark, setDark] = useState(() => localStorage.getItem('darkMode') === 'true');

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
    localStorage.setItem('darkMode', String(dark));
  }, [dark]);

  useEffect(() => {
    if (!user?.id) {
      setProfile(null);
      setProfileLoadedFor(null);
      return undefined;
    }

    let cancelled = false;
    setProfileLoadedFor(user.id);
    api.get('/auth/me')
      .then((response) => {
        if (!cancelled) setProfile(response.data);
      })
      .catch(() => {
        if (!cancelled) setProfile(null);
      });
    return () => {
      cancelled = true;
    };
  }, [user?.id]);

  const activeProfile = profileLoadedFor === user?.id ? profile : null;
  const role = activeProfile?.role ?? user?.role;
  const roleLabel = ROLE_LABELS[role] || role || 'Пользователь';
  const fullName = activeProfile?.full_name || roleLabel;
  const email = activeProfile?.email || '';
  const initial = (activeProfile?.full_name || roleLabel)[0]?.toUpperCase() ?? 'П';

  const handleNavItem = (id) => {
    setIsMobileMenuOpen(false);
    onNavChange?.(id);
  };

  return (
    <div className="flex h-screen overflow-hidden bg-transparent">
      {/* Mobile overlay backdrop */}
      {isMobileMenuOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/50 md:hidden"
          onClick={() => setIsMobileMenuOpen(false)}
        />
      )}

      {/* ── Боковая панель ── */}
      <aside
        className={[
          'fixed inset-y-0 left-0 z-40 w-60 flex-shrink-0 flex flex-col transition-transform duration-200',
          'md:relative md:translate-x-0 md:z-auto',
          isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full'
        ].join(' ')}
        style={{ backgroundColor: dark ? '#1a1a1a' : '#1a2332' }}
      >
        {/* Логотип */}
        <div className="px-5 py-4 flex-shrink-0 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-brand-600 flex items-center justify-center flex-shrink-0">
            <span className="text-white text-xs font-extrabold tracking-tight leading-none">ВКР</span>
          </div>
          <div className="leading-none flex-1">
            <span className="text-white text-base font-bold tracking-tight">ВКР</span>
            <span className="text-brand-400 text-base font-bold tracking-tight">.Формат</span>
          </div>
          {/* Кнопка закрытия на мобильных */}
          <button
            className="md:hidden text-white/60 hover:text-white p-1 -mr-1 shrink-0"
            onClick={() => setIsMobileMenuOpen(false)}
            aria-label="Закрыть меню"
          >
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
              <path d="M4 4l10 10M14 4L4 14" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
          </button>
        </div>

        {/* Разделитель */}
        {navItems.length > 0 && (
          <div className="mx-4 h-px bg-white/10" />
        )}

        {/* Навигация */}
        <nav className="flex-1 px-3 py-3 space-y-0.5 overflow-y-auto">
          {navItems.map((item) => {
            const active = activeView === item.id;
            return (
              <button
                key={item.id}
                onClick={() => handleNavItem(item.id)}
                className={[
                  'w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors text-left',
                  active
                    ? 'bg-brand-600 text-white'
                    : 'text-slate-400 hover:bg-white/10 hover:text-white'
                ].join(' ')}
              >
                {NAV_ICONS[item.id] ?? null}
                <span className="flex-1">{item.label}</span>
                {item.badge && (
                  <span className="w-2 h-2 rounded-full bg-red-500 shrink-0" />
                )}
              </button>
            );
          })}
        </nav>

        {/* Переключатель темы */}
        <div className="px-4 pb-2 flex-shrink-0">
          <button
            type="button"
            onClick={() => setDark((v) => !v)}
            className="flex items-center gap-2 text-slate-400 hover:text-white text-xs transition-colors py-1"
            title={dark ? 'Светлая тема' : 'Тёмная тема'}
          >
            {dark ? (
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <circle cx="7" cy="7" r="3" stroke="currentColor" strokeWidth="1.4"/>
                <path d="M7 1v1.5M7 11.5V13M1 7h1.5M11.5 7H13M2.9 2.9l1.05 1.05M10.05 10.05l1.05 1.05M2.9 11.1l1.05-1.05M10.05 3.95l1.05-1.05" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
              </svg>
            ) : (
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M12 7.5A5.5 5.5 0 016.5 2a5.5 5.5 0 100 11A5.5 5.5 0 0012 7.5z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round"/>
              </svg>
            )}
            {dark ? 'Светлая' : 'Тёмная'}
          </button>
        </div>

        {/* Профиль пользователя / выход */}
        <div className="px-3 py-3 flex-shrink-0 border-t border-white/10">
          <div className="flex items-start gap-3 px-2 py-2 rounded-lg">
            <div className="w-9 h-9 rounded-full bg-brand-600 flex items-center justify-center text-white text-sm font-bold flex-shrink-0">
              {initial}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-white text-sm font-medium leading-snug break-words">{fullName}</p>
              <p className="text-slate-400 text-xs truncate">{roleLabel}</p>
              {email && <p className="text-slate-500 text-[11px] truncate">{email}</p>}
              <button
                onClick={logout}
                className="mt-1 text-slate-400 text-xs hover:text-white transition-colors"
              >
                Выйти
              </button>
            </div>
          </div>
        </div>
      </aside>

      {/* ── Область контента ── */}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        {/* Верхняя панель на мобильных */}
        <div className="shrink-0 flex items-center gap-3 px-4 py-3 border-b border-gray-200 dark:border-[#3a3a3a] bg-white dark:bg-[#1e1e1e] md:hidden">
          <button
            onClick={() => setIsMobileMenuOpen(true)}
            className="text-gray-600 hover:text-gray-900 p-1 -m-1"
            aria-label="Открыть меню"
          >
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <path d="M3 5h14M3 10h14M3 15h14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
            </svg>
          </button>
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded bg-brand-600 flex items-center justify-center flex-shrink-0">
              <span className="text-white text-[9px] font-extrabold tracking-tight">ВКР</span>
            </div>
            <span className="text-sm font-bold text-gray-900">ВКР<span className="text-brand-500">.Формат</span></span>
          </div>
        </div>

        {/* Основной контент */}
        <main className="flex-1 min-w-0 overflow-hidden flex flex-col">
          {children}
        </main>
      </div>
    </div>
  );
}

export default Layout;
