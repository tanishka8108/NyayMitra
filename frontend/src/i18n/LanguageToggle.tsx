/* =========================================================
   LANGUAGE TOGGLE — English / मराठी

   A compact two-segment pill. Mirrors ThemeToggle's
   construction: a real button per language with
   aria-pressed, the shared focus ring, and a sliding
   highlight that animates (respecting reduced motion via
   the global guard in index.css).
   ========================================================= */

import { useT } from "./context";
import "./LanguageToggle.css";

export default function LanguageToggle() {
  const { lang, setLang, t } = useT();

  return (
    <div
      className="lang-toggle"
      role="group"
      aria-label={t("app.lang.group")}
    >
      <button
        type="button"
        lang="en"
        className={lang === "en" ? "is-active" : ""}
        aria-pressed={lang === "en"}
        onClick={() => setLang("en")}
      >
        EN
      </button>
      <button
        type="button"
        lang="mr"
        className={lang === "mr" ? "is-active" : ""}
        aria-pressed={lang === "mr"}
        onClick={() => setLang("mr")}
      >
        मराठी
      </button>
    </div>
  );
}
