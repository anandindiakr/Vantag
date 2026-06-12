import { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useRegion } from '../hooks/useRegion';

interface Props {
  /** 'light' = dark text (for light backgrounds), 'dark' = white text (for dark/nav) */
  variant?: 'light' | 'dark';
}

export function LanguageSelector({ variant = 'dark' }: Props) {
  const { i18n } = useTranslation();
  const region = useRegion();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const currentLang =
    region.languages.find((l) => l.code === i18n.language) ||
    region.languages[0];

  const changeLang = (code: string) => {
    i18n.changeLanguage(code);
    localStorage.setItem('vantag_lang', code);
    setOpen(false);
  };

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const textCls =
    variant === 'dark'
      ? 'text-white/80 hover:text-white'
      : 'text-gray-600 hover:text-gray-900';

  const dropdownCls =
    'absolute right-0 mt-1 w-44 rounded-xl shadow-xl border border-white/10 bg-gray-900/95 backdrop-blur-sm z-50 py-1';

  if (region.languages.length <= 1) return null;

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className={`flex items-center gap-1.5 text-sm font-medium px-2 py-1 rounded-lg transition-colors ${textCls}`}
        aria-label="Select language"
      >
        <svg className="w-4 h-4 opacity-70" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129" />
        </svg>
        <span>{currentLang.label}</span>
        <svg className={`w-3 h-3 transition-transform ${open ? 'rotate-180' : ''}`} fill="currentColor" viewBox="0 0 20 20">
          <path fillRule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd" />
        </svg>
      </button>

      {open && (
        <div className={dropdownCls}>
          {region.languages.map((lang) => (
            <button
              key={lang.code}
              onClick={() => changeLang(lang.code)}
              className={`w-full text-left px-4 py-2 text-sm transition-colors ${
                lang.code === i18n.language
                  ? 'text-white bg-white/10 font-semibold'
                  : 'text-gray-300 hover:bg-white/5 hover:text-white'
              }`}
            >
              {lang.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
