/* eslint-disable react-refresh/only-export-components -- a provider, its hook and the catalogue live together */
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

/**
 * Tamil / English (MP15). The English text is the key (gettext style): a string with no Tamil entry falls back to
 * English, so nothing is ever blank. Numbers, units, rupee amounts, item codes and document numbers are never
 * translated. The language is remembered on this device. Every Tamil string below NEEDS FLUENT REVIEW: it was
 * written for the DEMO and has not been checked by a fluent speaker (docs/i18n-gaps.md lists what is not covered).
 */
export type Lang = "en" | "ta";

const TA: Record<string, string> = {
  // top bar and shell
  "Sign in": "உள்நுழை",
  "Sign out": "வெளியேறு",
  "Restart tour": "சுற்றுலாவை மீண்டும் தொடங்கு",
  Menu: "பட்டியல்",
  "Skip to content": "உள்ளடக்கத்திற்குச் செல்",
  // menu groups
  Guide: "வழிகாட்டி",
  Salesman: "விற்பனையாளர்",
  Admin: "நிர்வாகம்",
  Production: "உற்பத்தி",
  Owner: "உரிமையாளர்",
  Auditor: "தணிக்கையாளர்",
  Judge: "நடுவர்",
  you: "நீங்கள்",
  // screen names
  "Start here": "இங்கே தொடங்கு",
  "Guided tour": "வழிகாட்டும் சுற்றுலா",
  Today: "இன்று",
  "New order": "புதிய ஆர்டர்",
  "My orders": "என் ஆர்டர்கள்",
  Summary: "சுருக்கம்",
  Freshness: "புத்துணர்ச்சி",
  "Order inbox": "ஆர்டர் பெட்டி",
  "Invoices and dispatch": "விலைப்பட்டியல் மற்றும் அனுப்புதல்",
  Collections: "வசூல்",
  "Trips and cost-to-serve": "பயணங்கள் மற்றும் சேவைச் செலவு",
  Purchases: "கொள்முதல்",
  "Batch card": "தொகுப்பு அட்டை",
  "Run costs": "தொகுப்புச் செலவுகள்",
  "Batch planner": "தொகுப்புத் திட்டமிடல்",
  "Trace and recall": "கண்டறிதல் மற்றும் திரும்பப் பெறுதல்",
  "Oil and fill weights": "எண்ணெய் மற்றும் நிரப்பு எடை",
  "Morning brief": "காலைச் சுருக்கம்",
  "Where profit leaks": "லாபம் எங்கே கசிகிறது",
  Reports: "அறிக்கைகள்",
  "Judge Mode": "நடுவர் முறை",
  // tour chrome
  "← Back": "← பின்",
  "Finish the tour": "சுற்றுலாவை முடி",
  "Take me there": "அங்கே அழைத்துச் செல்",
  "Start the guided tour →": "வழிகாட்டும் சுற்றுலாவைத் தொடங்கு →",
  "You have finished the guided tour": "வழிகாட்டும் சுற்றுலாவை முடித்துவிட்டீர்கள்",
  "Create your own factory": "உங்கள் சொந்தத் தொழிற்சாலையை உருவாக்கு",
  "Sign in to my account": "என் கணக்கில் உள்நுழை",
  "Restart the tour": "சுற்றுலாவை மீண்டும் தொடங்கு",
  // home
  "Every gram traced. Every rupee explained.":
    "ஒவ்வொரு கிராமும் கண்டறியப்படும். ஒவ்வொரு ரூபாயும் விளக்கப்படும்.",
  "See what gets checked": "என்ன சரிபார்க்கப்படுகிறது என்று பார்",
  // sign-in
  Email: "மின்னஞ்சல்",
  Password: "கடவுச்சொல்",
  "Signing in…": "உள்நுழைகிறது…",
  "Signed in": "உள்நுழைந்துவிட்டீர்கள்",
  "Go to my home screen": "என் முகப்புத் திரைக்குச் செல்",
};

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
      title={lang === "en" ? "Tamil (needs fluent review)" : "English"}
      onClick={() => setLang(lang === "en" ? "ta" : "en")}
    >
      {lang === "en" ? "தமிழ்" : "English"}
    </button>
  );
}
