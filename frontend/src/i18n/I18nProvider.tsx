/* =========================================================
   I18N PROVIDER

   Mounts the language context around the app (see
   main.tsx). Keeps <html lang> in step with the choice so
   assistive technology announces the right language.
   ========================================================= */

import {
  useEffect,
  useMemo,
  type ReactNode,
} from "react";

import {
  I18nContext,
  makeT,
  makeTm,
  useLangState,
} from "./context";

export function I18nProvider({
  children,
}: {
  children: ReactNode;
}) {
  const [lang, setLang] = useLangState();

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const value = useMemo(
    () => ({ lang, setLang, t: makeT(lang), tm: makeTm(lang) }),
    [lang, setLang],
  );

  return (
    <I18nContext.Provider value={value}>
      {children}
    </I18nContext.Provider>
  );
}
