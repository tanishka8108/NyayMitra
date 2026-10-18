/* =========================================================
   I18N CONTEXT — language state, `t()` lookup, `tm()` map

   Split from the provider so this module exports no
   components (react-refresh) — components import `useT`
   from here, and main.tsx mounts <I18nProvider>.
   ========================================================= */

import { createContext, useCallback, useContext, useState } from "react";

import { en } from "./en";
import { mr } from "./mr";
import { MESSAGE_MAP } from "./messages";

export type Lang = "en" | "mr";

const DICTS: Record<Lang, Record<string, string>> = { en, mr };

const STORAGE_KEY = "nyaymitra.lang";

export type TParams = Record<string, string | number>;

export interface I18nValue {
  lang: Lang;
  setLang: (next: Lang) => void;
  t: (key: string, params?: TParams) => string;
  tm: (message: string) => string;
}

export const I18nContext = createContext<I18nValue | null>(null);

/* Outside a provider (unit tests rendering a bare page) the
   layer degrades to English instead of crashing. */
const ENGLISH_ONLY: I18nValue = {
  lang: "en",
  setLang: () => {},
  t: (key, params) => {
    let text = en[key] ?? key;
    if (params) {
      for (const [name, value] of Object.entries(params)) {
        text = text.split(`{${name}}`).join(String(value));
      }
    }
    return text;
  },
  tm: (message) => message,
};

/** Language state for the first render (persisted choice). */
export function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "mr" || saved === "en") return saved;
  } catch {
    /* storage unavailable (private mode) — English */
  }
  return "en";
}

/** Persist the choice; called by the provider's setLang. */
export function persistLang(next: Lang): void {
  try {
    localStorage.setItem(STORAGE_KEY, next);
  } catch {
    /* storage unavailable — the session keeps it */
  }
}

/** The `t` for a language: dictionary lookup + {params}. */
export function makeT(lang: Lang) {
  return (key: string, params?: TParams): string => {
    let text = DICTS[lang][key] ?? en[key] ?? key;

    if (params) {
      for (const [name, value] of Object.entries(params)) {
        text = text.split(`{${name}}`).join(String(value));
      }
    }

    return text;
  };
}

/** Translate a known backend/validation sentence; else pass through. */
export function makeTm(lang: Lang) {
  return (message: string): string =>
    lang === "en" ? message : MESSAGE_MAP[message] ?? message;
}

/** Small state helper shared by the provider. */
export function useLangState(): [Lang, (next: Lang) => void] {
  const [lang, setLangState] = useState<Lang>(initialLang);

  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    persistLang(next);
  }, []);

  return [lang, setLang];
}

/** Full i18n control: `{ lang, setLang, t, tm }`. */
export function useT(): I18nValue {
  return useContext(I18nContext) ?? ENGLISH_ONLY;
}
