/* =========================================================
   NYAYMITRA — COURT ORDER EXPLANATION

   Two calls to the NLP service. The service recognises the
   standing language an order is written in and restates it
   plainly, and every answer arrives in three layers:

       Original legal text  →  Simple English  →  मराठी / हिंदी

   The third layer only exists when a language was asked for, and
   it is the *plain* layer that gets translated — legalese does
   not survive a translation model, everyday words do.

   Extraction is allowed to fail — a scanned image on a host
   without OCR simply cannot be read — and that failure comes
   back as a normal answer with a reason attached, so the
   screen can ask the person for the text instead of showing
   an error for something that was never wrong.
   ========================================================= */

import {
  TRANSLATION_API_BASE_URL,
  TRANSLATION_API_KEY,
} from "./config";

export interface ExtractResult {
  ok: boolean;
  text: string;
  needs_text: boolean;
  reason: string;
}

export interface ExplainPoint {
  heading: string;
  plain: string;
}

export interface ExplainTerm {
  term: string;
  plain: string;
}

/** What a translation did, when one was asked for. */
export interface ExplainTranslation {
  requested: string;
  applied: boolean;
  reason: string;
  /** Which layer the model was given — always the simple one. */
  layer?: string;
}

/**
 * The three layers one piece of text is offered in:
 *
 *     legal       the order as the court wrote it
 *     simple      the same words, in everyday English
 *     translated  that plain English in the requested language
 *
 * `translated` is null until a language other than English is asked
 * for, and every field is null for a section the document lacks.
 */
export interface CourtOrderLayers {
  legal: string | null;
  simple: string | null;
  translated: string | null;
}

export interface ExplainResult {
  filename: string;
  summary: string;
  points: ExplainPoint[];
  key_dates: string[];
  terms: ExplainTerm[];
  disclaimer: string;
  language?: string;
  layers?: CourtOrderLayers;
  translation?: ExplainTranslation;
}

async function readDetail(
  response: Response,
  fallback: string,
): Promise<string> {
  try {
    const payload: unknown = await response.json();

    if (
      payload &&
      typeof payload === "object" &&
      "detail" in payload &&
      typeof payload.detail === "string"
    ) {
      return payload.detail;
    }
  } catch {
    /* Not JSON — keep the fallback. */
  }

  return `${fallback} (status ${response.status})`;
}

/** Best-effort text out of an uploaded order. */
export async function extractOrderText(
  file: File,
): Promise<ExtractResult> {
  const body = new FormData();
  body.append("file", file, file.name);

  const response = await fetch(
    `${TRANSLATION_API_BASE_URL}/api/court-order/extract`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${TRANSLATION_API_KEY}` },
      body,
    },
  );

  if (!response.ok) {
    throw new Error(
      await readDetail(response, "The file could not be read."),
    );
  }

  return (await response.json()) as ExtractResult;
}

/** Plain-language reading of an order's text, in three layers. */
export async function explainOrderText(
  text: string,
  filename: string,
  language = "en",
): Promise<ExplainResult> {
  const response = await fetch(
    `${TRANSLATION_API_BASE_URL}/api/court-order/explain`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${TRANSLATION_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ text, filename, language }),
    },
  );

  if (!response.ok) {
    throw new Error(
      await readDetail(response, "The order could not be explained."),
    );
  }

  return (await response.json()) as ExplainResult;
}

/* =========================================================
   UPLOADED DOCUMENT

   One call instead of two: the service validates the PDF,
   scans it, reads it (OCR for a scanned page), splits it into
   the five sections a court order is written in, and explains
   each. Every section comes back even when the document does
   not contain it, so the screen can say "not in this
   document" rather than leaving a hole.
   ========================================================= */

export interface CourtOrderParagraph {
  number: number | null;
  text: string;
}

export interface CourtOrderSection {
  section_id: string;
  title: string;
  available: boolean;
  text: string | null;
  /** The middle layer, also carried inside `layers`. */
  simple_text?: string | null;
  layers?: CourtOrderLayers;
  paragraphs: CourtOrderParagraph[];
  page_start: number | null;
  page_end: number | null;
  explanation: ExplainPoint[];
  key_dates: string[];
  note: string;
  translated_text?: string | null;
}

export interface CourtOrderMetadata {
  ocr_used: boolean;
  page_count: number;
  security_scan: { scanned: boolean; status: string };
  extraction: { direct_pages: number; ocr_pages: number[] };
  text_characters: number;
  sections_found: number;
}

export interface UploadExplainResult {
  success: boolean;
  filename: string;
  language: string;
  summary: string;
  /** The document's three layers: legal → simple English → translated. */
  layers?: CourtOrderLayers;
  sections: CourtOrderSection[];
  metadata: CourtOrderMetadata;
  points: ExplainPoint[];
  key_dates: string[];
  terms: ExplainTerm[];
  disclaimer: string;
  translation?: ExplainTranslation;
}

/** Read a court order PDF and explain it, in one request. */
export async function explainOrderUpload(
  file: File,
  language = "en",
): Promise<UploadExplainResult> {
  const body = new FormData();
  body.append("file", file, file.name);
  body.append("language", language);

  const response = await fetch(
    `${TRANSLATION_API_BASE_URL}/api/court-order/explain`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${TRANSLATION_API_KEY}` },
      body,
    },
  );

  if (!response.ok) {
    /* The service's message is written for the person who uploaded:
       "not a PDF", "too large", "could not be accepted for security
       reasons" — never an internal detail. */
    throw new Error(
      await readDetail(response, "The court order could not be read."),
    );
  }

  return (await response.json()) as UploadExplainResult;
}
