# NyayMitra UI localization (English / मराठी)

## Mechanism

- `src/i18n/en.ts` — English strings, flat dotted keys.
- `src/i18n/mr.ts` — मराठी strings, same keys.
- `src/i18n/context.ts` + `src/i18n/I18nProvider.tsx` —
  language context, `I18nProvider` (mounted in `main.tsx`)
  and `useT()`.
  `const { t } = useT();` inside a component, then
  `t("nav.home")` or `t("cases.count", { n })` for
  `{placeholders}`.
- `src/i18n/LanguageToggle.tsx` — the EN / मराठी pill,
  mounted in the signed-out auth corner, the signed-in
  session bar, and the role-dashboard shell header.
- `src/i18n/messages.ts` — `MESSAGE_MAP`: known English
  backend/validation sentences → मराठी, applied via
  `tm(message)`; unknown sentences pass through unchanged.

The selected language persists in `localStorage`
(`nyaymitra.lang`), survives route changes and refreshes,
and sets `<html lang>` for assistive technology. No new
dependencies.

## Fallback and missing keys

`t(key)` falls back to the English string, then to the key
itself, so a gap degrades to readable English rather than
blank UI. `i18n.test.ts` enforces full key parity between
`en.ts` and `mr.ts` and rejects empty values — a key added
without its मराठी twin fails the test suite. Dynamic
messages not present in `MESSAGE_MAP` display in English
(this is the documented gap list: see `MESSAGE_MAP` itself;
it is currently empty beyond mapped entries added with each
page).

## Scope

Interface text only: navigation, headings, buttons, form
labels, placeholders, statuses, empty/loading/error copy,
modals and accessible names. User-generated content — case
descriptions, legal documents, lawyer names, addresses —
is never translated automatically.
