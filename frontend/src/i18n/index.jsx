import { useCallback, useEffect, useState, createContext, useContext } from "react";
import zhCN from "./zh-CN.js";
import enUS from "./en-US.js";

const LOCALES = { "zh-CN": zhCN, "en-US": enUS };
const STORAGE_KEY = "medical_assistant_locale";
const DEFAULT_LOCALE = "zh-CN";

const I18nContext = createContext(null);

function getInitialLocale() {
  if (typeof window === "undefined") return DEFAULT_LOCALE;
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored && LOCALES[stored]) return stored;
  const browser = navigator.language;
  if (browser.startsWith("zh")) return "zh-CN";
  if (browser.startsWith("en")) return "en-US";
  return DEFAULT_LOCALE;
}

export function I18nProvider({ children }) {
  const [locale, setLocaleState] = useState(getInitialLocale);
  const messages = LOCALES[locale] || zhCN;

  const setLocale = useCallback((loc) => {
    if (LOCALES[loc]) {
      setLocaleState(loc);
      localStorage.setItem(STORAGE_KEY, loc);
    }
  }, []);

  // Simple interpolation: replaces {key} in string
  const t = useCallback(
    (key, params) => {
      let text = messages[key] || zhCN[key] || key;
      if (params) {
        Object.entries(params).forEach(([k, v]) => {
          text = text.replace(new RegExp(`\\{${k}\\}`, "g"), v);
        });
      }
      return text;
    },
    [messages],
  );

  useEffect(() => {
    document.documentElement.setAttribute("lang", locale);
  }, [locale]);

  return (
    <I18nContext.Provider value={{ locale, setLocale, t, locales: Object.keys(LOCALES) }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}
