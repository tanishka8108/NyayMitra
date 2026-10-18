/* =========================================================
   NYAYMITRA — THEME STORE

   One source of truth for light/dark across the app.

   - The chosen theme is persisted under `nyaymitra.theme`,
     the same localStorage convention as the session
     (`nyaymitra.session`) and the case store
     (`nyaymitra.cases.*`).
   - The active theme is expressed as `<html data-theme>`,
     which index.html's inline script has already set before
     first paint (no flash on load); this module takes over
     after hydration and keeps the attribute in sync.
   - First visit (nothing stored) follows the system
     preference via `prefers-color-scheme`.
   - Switching only flips the attribute — no reload, no
     re-render of the route tree.

   Read with `useTheme()`. It is a plain external store, not
   a context, so every component (and every existing test
   render) works without a provider wrapper.
   ========================================================= */

import { useSyncExternalStore } from "react";

export type Theme = "light" | "dark";

const THEME_KEY = "nyaymitra.theme";
const CHANGE_EVENT = "nyaymitra:theme-change";

function systemTheme(): Theme {
  if (typeof window === "undefined" || !window.matchMedia) return "light";

  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

/** The current theme: stored choice, else the system preference. */
export function getTheme(): Theme {
  try {
    const stored = localStorage.getItem(THEME_KEY);

    if (stored === "light" || stored === "dark") return stored;
  } catch {
    /* Storage unavailable — fall through to the system preference. */
  }

  return systemTheme();
}

function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute("data-theme", theme);

  window.dispatchEvent(
    new CustomEvent(CHANGE_EVENT, { detail: theme }),
  );
}

/** Choose and persist the theme; every `useTheme()` updates live. */
export function setTheme(theme: Theme): void {
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* Storage unavailable — the theme still applies for this visit. */
  }

  applyTheme(theme);
}

/** Flip light ↔ dark. */
export function toggleTheme(): void {
  setTheme(getTheme() === "dark" ? "light" : "dark");
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, onChange);

  return () => window.removeEventListener(CHANGE_EVENT, onChange);
}

/**
 * `[theme, setTheme]` — reactive across every component that
 * reads it. The server snapshot mirrors index.html's default
 * so hydration never disagrees with the first paint.
 */
export function useTheme(): [Theme, (theme: Theme) => void] {
  const theme = useSyncExternalStore(
    subscribe,
    getTheme,
    () => "light" as Theme,
  );

  return [theme, setTheme];
}
