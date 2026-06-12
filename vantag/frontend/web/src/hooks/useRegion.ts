import { useMemo, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { detectRegion, type RegionConfig } from '../config/regions';

let _cached: RegionConfig | null = null;

export function useRegion(): RegionConfig {
  if (!_cached) {
    _cached = detectRegion();
  }
  const region = _cached;

  const { i18n } = useTranslation();

  // On first mount, switch i18n to the region's default language
  // (only if user hasn't already picked a language)
  useEffect(() => {
    const stored = localStorage.getItem('vantag_lang');
    if (stored && region.languages.some((l) => l.code === stored)) {
      if (i18n.language !== stored) i18n.changeLanguage(stored);
    } else {
      // Stored value absent or not valid for this region — use region default and persist it
      i18n.changeLanguage(region.defaultLang);
      localStorage.setItem('vantag_lang', region.defaultLang);
    }
  }, [region.defaultLang, i18n]);

  return useMemo(() => region, [region]);
}
