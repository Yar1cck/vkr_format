import React, { Suspense, lazy } from 'react';

import useAuthStore from './store/auth';
import AuthPage from './pages/AuthPage';

// По роли в сессии загружается ровно одна из тяжёлых страниц
// (Student/Staff/Admin) — eager-импорт всех трёх тащит ненужный
// код в начальный bundle. lazy() режет это на отдельные чанки.
const StudentPage = lazy(() => import('./pages/StudentPage'));
const StaffPage = lazy(() => import('./pages/StaffPage'));
const AdminPage = lazy(() => import('./pages/AdminPage'));

function PageFallback() {
  return (
    <div className="flex items-center justify-center min-h-screen text-slate-400 text-sm">
      Загрузка…
    </div>
  );
}

function App() {
  const { user } = useAuthStore();

  if (!user) {
    return <AuthPage />;
  }

  let page;
  if (user.role === 'student') {
    page = <StudentPage />;
  } else if (user.role === 'supervisor') {
    page = <StaffPage title="Кабинет научного руководителя" />;
  } else if (user.role === 'dean') {
    page = <StaffPage title="Кабинет деканата" />;
  } else {
    page = <AdminPage />;
  }

  return <Suspense fallback={<PageFallback />}>{page}</Suspense>;
}

export default App;
