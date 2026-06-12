/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        'vantag-red':   '#EF4444',
        'vantag-amber': '#F59E0B',
        'vantag-green': '#10B981',
        'vantag-dark':  '#0F172A',
        'vantag-card':  '#1E293B',
      },
      animation: {
        'pulse-border': 'pulse-border 1.5s ease-in-out infinite',
        'fade-in': 'fade-in 0.3s ease-in-out',
        'slide-in': 'slide-in 0.25s ease-out',
      },
      keyframes: {
        'pulse-border': {
          '0%, 100%': { borderColor: 'rgba(239, 68, 68, 0.8)' },
          '50%':       { borderColor: 'rgba(239, 68, 68, 0.2)' },
        },
        'fade-in': {
          from: { opacity: '0', transform: 'translateY(4px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-in': {
          from: { opacity: '0', transform: 'translateX(-8px)' },
          to:   { opacity: '1', transform: 'translateX(0)' },
        },
      },
    },
  },
  plugins: [],
};
