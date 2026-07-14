/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Основная палитра МИИГАиК (Pantone 2747 C, #001a72)
        sidebar: '#001a72',
        brand: {
          50:  '#e7e9f3',
          100: '#c3c8e6',
          200: '#8799cc',
          300: '#4b6bb3',
          400: '#103d99',
          500: '#001680',
          600: '#001a72',  // PRIMARY — кнопки, активные элементы
          700: '#001460',
          800: '#000e4d',
          900: '#00083a',
        },
        // Красный МИИГАиК (Pantone 2035 C, #d6001c) — ошибки, danger-состояния
        danger: {
          50:  '#fdf0f1',
          100: '#fad5d8',
          200: '#f5acb2',
          500: '#d6001c',
          600: '#d6001c',
          700: '#b30018',
        },
        // Серый МИИГАиК (Pantone 7544 C, #8996a0) — вторичные элементы
        'miigaik-gray': '#8996a0',
        // Светлый МИИГАиК (Pantone Cool Gray 1 C, #f3f3f1) — фон страницы
        'miigaik-light': '#f3f3f1',
      },
      fontFamily: {
        sans: ['"Montserrat"', '"Segoe UI"', 'system-ui', 'sans-serif'],
      },
      fontSize: {
        // Чуть крупнее базовых Tailwind-значений
        'xs':   ['0.8125rem', { lineHeight: '1.45' }],  // 13px  (было 12px)
        'sm':   ['0.9375rem', { lineHeight: '1.55' }],  // 15px  (было 14px)
        'base': ['1.0625rem', { lineHeight: '1.65' }],  // 17px  (было 16px)
      },
      boxShadow: {
        panel: '0 1px 4px rgba(0,0,0,0.08), 0 4px 16px rgba(0,0,0,0.06)',
      },
    },
  },
  plugins: [],
};
