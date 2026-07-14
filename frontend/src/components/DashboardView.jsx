import React from 'react';

import { fmtDateCompact } from '../utils/format';
import { STATUS_LABELS } from '../utils/labels';

const KPI_COLORS = ['border-brand-500', 'border-emerald-500', 'border-violet-500', 'border-amber-500'];

const CATEGORY_COLORS = [
  { dot: 'bg-indigo-500',  bar: 'bg-indigo-500',  text: 'text-indigo-600' },
  { dot: 'bg-violet-500',  bar: 'bg-violet-500',  text: 'text-violet-600' },
  { dot: 'bg-emerald-500', bar: 'bg-emerald-500', text: 'text-emerald-600' },
  { dot: 'bg-amber-500',   bar: 'bg-amber-500',   text: 'text-amber-600' },
  { dot: 'bg-sky-500',     bar: 'bg-sky-500',     text: 'text-sky-600' },
  { dot: 'bg-rose-500',    bar: 'bg-rose-500',    text: 'text-rose-600' },
  { dot: 'bg-teal-500',    bar: 'bg-teal-500',    text: 'text-teal-600' },
  { dot: 'bg-lime-500',    bar: 'bg-lime-500',    text: 'text-lime-700' },
  { dot: 'bg-cyan-500',    bar: 'bg-cyan-500',    text: 'text-cyan-600' },
  { dot: 'bg-slate-400',   bar: 'bg-slate-400',   text: 'text-slate-500' },
];

// На Dashboard цветовая палитра статусов отличается от Staff (синий для
// processing, жёлтый для pending) — оставляем локально, чтобы не размывать
// общий STATUS_DOT в utils/labels.
const STATUS_DOT = {
  done:       'bg-emerald-500',
  pending:    'bg-amber-500',
  processing: 'bg-blue-500',
  error:      'bg-red-500',
};

function KpiCard({ label, value, sub, accent, onClick }) {
  return (
    <div
      className={`card border-t-4 ${accent} flex flex-col gap-1 ${onClick ? 'cursor-pointer hover:shadow-md transition-shadow select-none' : ''}`}
      onClick={onClick}
    >
      <span className="text-3xl font-bold text-gray-900 tabular-nums">{value}</span>
      <span className="text-sm text-slate-500 leading-snug">{label}</span>
      {sub && <span className="text-xs text-slate-400">{sub}</span>}
      {onClick && <span className="text-xs text-brand-600 mt-1">Открыть список →</span>}
    </div>
  );
}

function BarChart({ data }) {
  const [hovered, setHovered] = React.useState(null);
  if (!data || data.length === 0) return null;

  const max = Math.max(...data.map((d) => d.count), 1);
  const W = 560;
  const CHART_H = 100;
  const LABEL_H = 18;
  const TOOLTIP_H = 22;
  const H_TOTAL = TOOLTIP_H + CHART_H + LABEL_H;
  const barW = Math.floor(W / data.length) - 1;

  // Show date labels only every ~5 bars to avoid crowding
  const labelStep = data.length <= 15 ? 1 : data.length <= 20 ? 2 : 5;

  const fmtLabel = (iso) => {
    const [, mm, dd] = iso.split('-');
    return `${dd}.${mm}`;
  };

  return (
    <svg
      viewBox={`0 0 ${W} ${H_TOTAL}`}
      width="100%"
      aria-label="График загрузок"
      style={{ overflow: 'visible' }}
    >
      {data.map((d, i) => {
        const h = Math.max(2, Math.round((d.count / max) * CHART_H));
        const x = i * (W / data.length) + 0.5;
        const y = TOOLTIP_H + CHART_H - h;
        const cx = x + barW / 2;
        const isHovered = hovered === i;

        return (
          <g key={d.date}>
            <rect
              x={x}
              y={y}
              width={barW}
              height={h}
              rx="2"
              fill={isHovered ? '#2563eb' : '#3b82f6'}
              opacity={isHovered ? 1 : 0.82}
              style={{ cursor: 'default', transition: 'fill 0.1s, opacity 0.1s' }}
              onMouseEnter={() => setHovered(i)}
              onMouseLeave={() => setHovered(null)}
            />

            {/* Tooltip above bar */}
            {isHovered && (
              <g>
                <rect
                  x={Math.min(Math.max(cx - 22, 0), W - 44)}
                  y={y - TOOLTIP_H + 2}
                  width="44"
                  height="18"
                  rx="4"
                  fill="#1e293b"
                />
                <text
                  x={Math.min(Math.max(cx, 22), W - 22)}
                  y={y - TOOLTIP_H + 15}
                  textAnchor="middle"
                  fill="white"
                  fontSize="11"
                  fontWeight="600"
                >
                  {d.count}
                </text>
              </g>
            )}

            {/* Date label below bar */}
            {i % labelStep === 0 && (
              <text
                x={cx}
                y={TOOLTIP_H + CHART_H + LABEL_H - 2}
                textAnchor="middle"
                fill="#94a3b8"
                fontSize="9"
              >
                {fmtLabel(d.date)}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

const FALLBACK_COLOR = { dot: 'bg-slate-400', bar: 'bg-slate-400', text: 'text-slate-500' };

function CategoryBreakdown({ data }) {
  if (!data || data.length === 0) {
    return <p className="text-sm text-slate-400">Нет данных</p>;
  }
  return (
    <ul className="space-y-3">
      {data.map((cat, i) => {
        const c = CATEGORY_COLORS[i] ?? FALLBACK_COLOR;
        return (
          <li key={cat.name} className="flex items-center gap-3 text-sm">
            <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${c.dot}`} />
            <span className="flex-1 text-slate-700">{cat.name}</span>
            <div className="w-32 h-1.5 bg-slate-100 rounded-full overflow-hidden">
              <div className={`h-full rounded-full ${c.bar}`} style={{ width: `${cat.percent}%` }} />
            </div>
            <span className={`w-8 text-right font-semibold ${c.text}`}>{cat.percent}%</span>
          </li>
        );
      })}
    </ul>
  );
}

function RecentUploadsTable({ rows }) {
  if (!rows || rows.length === 0) {
    return <p className="text-sm text-slate-400">Нет загрузок</p>;
  }

  const fmtDate = fmtDateCompact;

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
            <th className="py-2 pr-4">Пользователь</th>
            <th className="py-2 pr-4">Тема / Файл</th>
            <th className="py-2 pr-4">Дата</th>
            <th className="py-2 pr-4">Нарушений</th>
            <th className="py-2">Статус</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-b border-slate-100 last:border-b-0">
              <td className="py-2 pr-4 font-medium">{row.owner_full_name}</td>
              <td className="py-2 pr-4 text-slate-600 max-w-xs truncate">{row.filename}</td>
              <td className="py-2 pr-4 text-slate-500">{fmtDate(row.uploaded_at)}</td>
              <td className="py-2 pr-4 text-slate-700">{row.violations ?? '—'}</td>
              <td className="py-2">
                <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium text-white ${STATUS_DOT[row.status] ?? 'bg-slate-400'}`}>
                  {STATUS_LABELS[row.status] ?? row.status}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DashboardView({ stats, activeVersionName, showStudents, onUsersClick, title = 'Обзор' }) {
  if (!stats) {
    return <p className="text-sm text-slate-400">Загрузка данных…</p>;
  }

  const kpis = [
    {
      label: 'Загружено документов',
      value: stats.total_documents.toLocaleString('ru-RU'),
      accent: KPI_COLORS[0],
    },
    {
      label: 'Нарушений исправлено',
      value: stats.total_auto_fixed?.toLocaleString('ru-RU') ?? '—',
      accent: KPI_COLORS[1],
    },
    {
      label: showStudents ? 'Студентов' : 'Пользователей',
      value: showStudents
        ? (stats.total_students?.toLocaleString('ru-RU') ?? stats.total_users.toLocaleString('ru-RU'))
        : stats.total_users.toLocaleString('ru-RU'),
      accent: KPI_COLORS[2],
      onClick: onUsersClick,
    },
    {
      label: 'Ср. нарушений / ВКР',
      value: stats.avg_violations?.toFixed(1) ?? '—',
      accent: KPI_COLORS[3],
    },
  ];

  return (
    <div className="p-8 space-y-6 overflow-auto h-full">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">{title}</h1>
        {activeVersionName && (
          <p className="mt-1 text-sm text-slate-500">
            Активная норм. база: <span className="font-medium text-slate-700">{activeVersionName}</span>
          </p>
        )}
      </div>

      {/* KPI row */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {kpis.map((k) => (
          <KpiCard key={k.label} {...k} onClick={k.onClick} />
        ))}
      </div>

      {/* Charts row */}
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="card lg:col-span-2">
          <h2 className="mb-4 text-sm font-semibold text-slate-700 uppercase tracking-wide">
            Загрузки за 30 дней
          </h2>
          <BarChart data={stats.uploads_30d} />
        </div>

        <div className="card">
          <h2 className="mb-4 text-sm font-semibold text-slate-700 uppercase tracking-wide">
            Нарушения по категориям
          </h2>
          <CategoryBreakdown data={stats.violations_by_category} />
        </div>
      </div>

      {/* Recent uploads */}
      <div className="card">
        <h2 className="mb-4 text-sm font-semibold text-slate-700 uppercase tracking-wide">
          Последние загрузки
        </h2>
        <RecentUploadsTable rows={stats.recent_uploads} />
      </div>
    </div>
  );
}

export default DashboardView;
