/* =========================================================
   MESSAGE MAP — known English sentences → मराठी

   Backend and api-layer messages arrive as finished
   English sentences (thrown Errors, alert bodies). This map
   translates the ones the UI is known to surface; `tm()`
   passes anything else through unchanged so a new server
   message still displays rather than disappearing.

   Documented fallback: untranslated messages show in
   English.
   ========================================================= */

export const MESSAGE_MAP: Record<string, string> = {};
