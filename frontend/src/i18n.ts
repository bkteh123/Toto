import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en.json";
import zh from "./locales/zh.json";

export type Lang = "zh" | "en";
const KEY = "ry_lang";

/** Per-viewer convenience only; storage can be blocked, so everything is guarded. */
export function savedLang(): Lang {
  try {
    const v = localStorage.getItem(KEY);
    if (v === "en" || v === "zh") return v;
  } catch {
    /* ignore */
  }
  return "zh"; // Simplified Chinese is the default
}

export function saveLang(lang: Lang): void {
  try {
    localStorage.setItem(KEY, lang);
  } catch {
    /* ignore */
  }
}

void i18n.use(initReactI18next).init({
  resources: { zh: { translation: zh }, en: { translation: en } },
  lng: savedLang(),
  fallbackLng: "en",
  interpolation: { escapeValue: false }, // React escapes
  returnNull: false,
});

export default i18n;
