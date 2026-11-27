/* eslint-disable react-refresh/only-export-components -- a provider, its hook and the catalogue live together */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { startTamil, stopTamil } from "./domTranslate";
import { TA } from "./ta";

/**
 * Tamil / English. The English text is the key (gettext style): a string with no Tamil entry falls back to English,
 * so nothing is ever blank. While Tamil is on, the page translator (domTranslate.ts) shows every screen in Tamil.
 * The language is remembered on this device.
 */
export type Lang = "en" | "ta";

const CATALOGUES: Record<Lang, Record<string, string>> = { en: {}, ta: TA };
const KEY = "aaharos.lang";

function initial(): Lang {
  try {
    return window.localStorage.getItem(KEY) === "ta" ? "ta" : "en";
  } catch {
    return "en";
  }
}

interface I18n {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (english: string) => string;
}

const I18nContext = createContext<I18n>({ lang: "en", setLang: () => undefined, t: (s) => s });

/** The English text when no translation exists (so a missing key is never blank). */
export function translate(lang: Lang, english: string): string {
  return CATALOGUES[lang][english] ?? english;
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initial);
  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    try {
      window.localStorage.setItem(KEY, next);
    } catch {
      /* storage blocked */
    }
    document.documentElement.lang = next;
  }, []);
  useEffect(() => {
    document.documentElement.lang = lang;
    if (lang === "ta") startTamil();
    else stopTamil();
  }, [lang]);
  const value = useMemo(
    () => ({ lang, setLang, t: (s: string) => translate(lang, s) }),
    [lang, setLang],
  );
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useT(): I18n {
  return useContext(I18nContext);
}

/** The switch in the top bar: shows the other language in its own script. */
export function LanguageSwitch() {
  const { lang, setLang } = useT();
  return (
    <button
      type="button"
      className="btn btn-ghost lang-switch"
      lang={lang === "en" ? "ta" : "en"}
      title={lang === "en" ? "தமிழ்" : "English"}
      onClick={() => setLang(lang === "en" ? "ta" : "en")}
    >
      {lang === "en" ? "தமிழ்" : "English"}
    </button>
  );
}
