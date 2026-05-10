/**
 * i18n bootstrap.
 *
 * - Detection order: localStorage (`tickora.lang`) → browser → fallback.
 * - Two locales today: `en` (fallback) and `ro` (Romanian).
 * - Translations live in `./locales/{en,ro}.json`. Keep keys nested by
 *   feature (e.g. `tickets.list.title`) so adding a new page doesn't
 *   pollute a flat namespace.
 *
 * Adding a third locale: drop a JSON file into `./locales/`, register it
 * in `resources` below, and add the language code to
 * `LanguageSwitcher`'s option list.
 */
import i18n from 'i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import { initReactI18next } from 'react-i18next';

import en from './locales/en.json';
import ro from './locales/ro.json';

export const SUPPORTED_LANGUAGES = ['en', 'ro'] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      ro: { translation: ro },
    },
    fallbackLng: 'en',
    supportedLngs: [...SUPPORTED_LANGUAGES],
    interpolation: {
      escapeValue: false, // React already escapes
    },
    detection: {
      order: ['localStorage', 'navigator', 'htmlTag'],
      caches: ['localStorage'],
      lookupLocalStorage: 'tickora.lang',
    },
    returnNull: false,
  });

export default i18n;
