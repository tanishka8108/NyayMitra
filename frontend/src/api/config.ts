import { loadSession } from "../auth/session";

/* =========================================================
   NYAYMITRA — CENTRAL API CONFIG

   Every service URL and credential in the frontend is
   read from here. No page should hardcode a URL or an
   API key again.

   Values come from frontend/.env (Vite inlines them at
   build time). See .env.example for documentation.
   ========================================================= */

/* =========================================================
   LAWYER SERVICE  (NyayMitra-feature-lawyer-api)
   FastAPI + PostgreSQL, port 8000
   ========================================================= */

export const LAWYER_API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

/* =========================================================
   MODEL API  (src/api.py)
   /understand-situation + /predict-delay, port 8000
   ========================================================= */

export const MODEL_API_BASE_URL: string =
  import.meta.env.VITE_MODEL_API_URL || "http://127.0.0.1:8000";

/* =========================================================
   NLP / TRANSLATION SERVICE  (NyayMitra-feature-nlp-translation)
   FastAPI + IndicTrans2, port 8001
   ========================================================= */

export const TRANSLATION_API_BASE_URL: string =
  import.meta.env.VITE_TRANSLATION_API_URL ||
  "http://127.0.0.1:8001";

export const TRANSLATION_API_KEY: string =
  import.meta.env.VITE_TRANSLATION_API_KEY ||
  "nyaymitra-local-test-2026";

/* =========================================================
   GENERIC JSON REQUEST

   Shared by every API module so error handling (FastAPI's
   `detail` field) stays consistent across the app.
   ========================================================= */

export async function apiRequest<T>(
  baseUrl: string,
  endpoint: string,
  options?: RequestInit,
): Promise<T> {
  /*
   * AUTHENTICATION
   *
   * Requests to the lawyer service (:8000) carry the signed-in
   * session token when there is one — this is how protected
   * endpoints (auth/me, chat, verification) see who is calling.
   * Callers may still override any header (their headers are
   * spread last), and endpoints that do not require a session
   * simply ignore the header. The NLP service uses its own
   * fetchers and its own API key — it never reaches this point.
   */
  const session =
    baseUrl === LAWYER_API_BASE_URL ? loadSession() : null;

  const response = await fetch(
    `${baseUrl}${endpoint}`,
    {
      ...options,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...(session?.token
          ? { Authorization: `Bearer ${session.token}` }
          : {}),
        ...(options?.headers || {}),
      },
    },
  );

  if (!response.ok) {
    let message =
      `Request failed with status ${response.status}.`;

    try {
      const errorData: unknown = await response.json();

      if (
        errorData &&
        typeof errorData === "object" &&
        "detail" in errorData &&
        typeof errorData.detail === "string"
      ) {
        message = errorData.detail;
      }
    } catch {
      /* Keep default HTTP error message. */
    }

    throw new Error(message);
  }

  return response.json() as Promise<T>;
}
