import { loadSession } from "../auth/session";
import { LAWYER_API_BASE_URL } from "./config";

/* =========================================================
   NYAYMITRA — CASE DOCUMENT RETRIEVAL

   The court's own files for one matter — orders, notices,
   judgments — which is a different thing from:

   - `documentApi`   the copies a citizen added to Case
                     documents (browser-local store), and
   - the case record's `orders` list — the docket entry for
     an order, which describes it without carrying the file.

   BACKEND CONTRACT — the shape this client is written
   against. The endpoint is NOT mounted in the lawyer service
   yet; if it lands differently, change this file only — the
   screens read through it.

     GET /api/cases/{cnr}/documents
     Authorization: Bearer <session token>   (when protected)

     200 { "success": true, "items": [ {
            "id":           required, stable identifier
            "cnr":          the matter it belongs to
            "title":        required, display name
            "document_type": optional — "Order", "Notice", …
            "issued_at":    optional — ISO date the court issued it
            "file_name":    optional
            "mime_type":    optional
            "size_bytes":   optional
            "view_url":     optional — authorized URL, or omit
            "download_url": optional — authorized URL, or omit
          } ] }
     401 signed out · 403 not permitted for this case
     404 unknown CNR, or the API is not connected

     An empty matter answers 200 with items: [] — so a 404 can
     be reported honestly as "not available" rather than being
     dressed up as "no documents".

   Rules the UI holds itself to (see CaseDocumentsSection):
   - render only fields the response actually carried;
   - View / Download appear only when the backend supplied a
     genuine URL — never one the client guesses or builds;
   - a missing endpoint reads as "not available yet", never as
     "no documents exist" and never as an error in the case;
   - development mock rows exist only behind
     VITE_CASE_DOCUMENTS_MOCK, only in dev builds, and the
     screen labels them DEMO so demo never passes as real.
   ========================================================= */

export interface CaseDocumentRecord {
  id: string;
  cnr: string;
  title: string;

  /* Every field below is optional evidence: if the backend did
     not send it, the screen shows nothing rather than a guess. */
  document_type?: string;
  issued_at?: string;
  file_name?: string;
  mime_type?: string;
  size_bytes?: number;

  /* Authorized URLs, present only when the backend supplied
     them. Sanitized before they ever reach an <a href>. */
  view_url?: string;
  download_url?: string;
}

export type CaseDocumentsStatus =
  | "loading"
  | "ready"
  | "empty"
  | "unavailable"
  | "signed-out"
  | "forbidden"
  | "error";

export interface CaseDocumentsResult {
  status: CaseDocumentsStatus;
  records: CaseDocumentRecord[];
  /** True only for the development-only mock rows. */
  demo: boolean;
}

export function caseDocumentsEndpoint(cnr: string): string {
  return `/api/cases/${encodeURIComponent(cnr)}/documents`;
}

/* Development-only demo rows. The `import.meta.env.DEV` guard
   means production builds never contain them at all, and the
   screen carries a DEMO banner whenever they are shown. */
const MOCK_DOCUMENTS: boolean =
  import.meta.env.DEV &&
  import.meta.env.VITE_CASE_DOCUMENTS_MOCK === "true";

/**
 * Accept only http(s) or root-relative URLs. Anything else
 * (a `javascript:` value, a stray token) is dropped rather
 * than rendered, so a malformed backend field can never
 * become an executable link.
 */
function safeUrl(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;

  const trimmed = value.trim();

  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  if (trimmed.startsWith("/") && !trimmed.startsWith("//")) {
    return trimmed;
  }

  return undefined;
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim()
    ? value.trim()
    : undefined;
}

function optionalSize(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : undefined;
}

function toRecord(value: unknown, cnr: string): CaseDocumentRecord | null {
  if (!value || typeof value !== "object") return null;

  const raw = value as Record<string, unknown>;
  const title = optionalString(raw.title);

  /* A row without a title has nothing honest to display —
     drop it instead of inventing a label. */
  if (!title) return null;

  return {
    id: optionalString(raw.id) ?? title,
    cnr: optionalString(raw.cnr) ?? cnr,
    title,
    document_type: optionalString(raw.document_type),
    issued_at: optionalString(raw.issued_at),
    file_name: optionalString(raw.file_name),
    mime_type: optionalString(raw.mime_type),
    size_bytes: optionalSize(raw.size_bytes),
    view_url: safeUrl(raw.view_url),
    download_url: safeUrl(raw.download_url),
  };
}

function mockResult(cnr: string): CaseDocumentsResult {
  return {
    status: "ready",
    demo: true,
    records: [
      {
        id: `demo-${cnr}-1`,
        cnr,
        title: "Sample interim order (demo record)",
        document_type: "Order",
        issued_at: "2026-04-20",
        file_name: "interim-order-sample.pdf",
        mime_type: "application/pdf",
        size_bytes: 246_144,
        /* No URLs: a demo row never links anywhere. */
      },
      {
        id: `demo-${cnr}-2`,
        cnr,
        title: "Sample notice of hearing (demo record)",
        document_type: "Notice",
        issued_at: "2026-06-11",
        file_name: "notice-of-hearing-sample.pdf",
        mime_type: "application/pdf",
        size_bytes: 98_304,
      },
    ],
  };
}

/**
 * Fetch the court's published documents for one CNR.
 * Never throws: every failure resolves into a status the
 * screen can explain in plain words.
 */
export async function fetchCaseDocuments(
  cnr: string,
  signal?: AbortSignal,
): Promise<CaseDocumentsResult> {
  if (MOCK_DOCUMENTS) {
    return mockResult(cnr);
  }

  if (typeof fetch !== "function") {
    return { status: "error", records: [], demo: false };
  }

  try {
    const session = loadSession();

    const response = await fetch(
      `${LAWYER_API_BASE_URL}${caseDocumentsEndpoint(cnr)}`,
      {
        signal,
        headers: {
          Accept: "application/json",
          ...(session?.token
            ? { Authorization: `Bearer ${session.token}` }
            : {}),
        },
      },
    );

    if (response.status === 401) {
      return { status: "signed-out", records: [], demo: false };
    }

    if (response.status === 403) {
      return { status: "forbidden", records: [], demo: false };
    }

    if (response.status === 404) {
      /* Either the route is not mounted yet or the CNR is
         unknown to it — both read the same to a reader:
         nothing to show, and not the case's fault. */
      return { status: "unavailable", records: [], demo: false };
    }

    if (!response.ok) {
      return { status: "error", records: [], demo: false };
    }

    let payload: unknown;

    try {
      payload = await response.json();
    } catch {
      return { status: "error", records: [], demo: false };
    }

    const items = Array.isArray(payload)
      ? payload
      : payload &&
          typeof payload === "object" &&
          Array.isArray((payload as { items?: unknown }).items)
        ? ((payload as { items: unknown[] }).items)
        : null;

    if (!items) {
      return { status: "error", records: [], demo: false };
    }

    const records = items
      .map((item) => toRecord(item, cnr))
      .filter((record): record is CaseDocumentRecord => record !== null);

    if (records.length === 0) {
      return { status: "empty", records: [], demo: false };
    }

    return { status: "ready", records, demo: false };
  } catch {
    /* Network failure, DNS, CORS, aborted request — the screen
       shows a plain "could not load" with a retry, and the
       detail stays here rather than reaching the reader. */
    return { status: "error", records: [], demo: false };
  }
}
