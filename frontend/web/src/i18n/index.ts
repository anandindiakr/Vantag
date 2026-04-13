import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import en from './locales/en.json';
import hi from './locales/hi.json';
import ms from './locales/ms.json';
import zh from './locales/zh.json';

i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, hi: { translation: hi }, ms: { translation: ms }, zh: { translation: zh } },
  lng: 'en',
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
});

export default i18n;
