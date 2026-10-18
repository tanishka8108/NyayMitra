/* =========================================================
   THEME TOGGLE

   Switches the app between the light and dark themes. The
   choice persists (localStorage, same convention as the
   session) and applies instantly — the `data-theme`
   attribute flips on <html> and every token-driven colour
   follows; the app never reloads.

   Accessible by construction:
   - a real <button> with an explicit aria-label naming the
     action ("Switch to dark theme" / "Switch to light
     theme"), not the current state alone;
   - keyboard focus uses the shared focus ring;
   - the icon is decorative (aria-hidden) — the label is the
     accessible name.
   ========================================================= */

import { useTheme } from "../theme/theme";
import { useT } from "../i18n/context";
import "./ThemeToggle.css";

function MoonIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2m0 16v2M4.93 4.93l1.41 1.41m11.32 11.32 1.41 1.41M2 12h2m16 0h2M4.93 19.07l1.41-1.41m11.32-11.32 1.41-1.41" />
    </svg>
  );
}

export default function ThemeToggle() {
  const [theme, setTheme] = useTheme();
  const { t } = useT();

  const next = theme === "dark" ? "light" : "dark";

  const label =
    next === "dark"
      ? t("app.theme.toDark")
      : t("app.theme.toLight");

  return (
    <button
      type="button"
      className="nm-theme-toggle"
      onClick={() => setTheme(next)}
      aria-label={label}
      title={label}
    >
      {theme === "dark" ? <SunIcon /> : <MoonIcon />}
    </button>
  );
}
