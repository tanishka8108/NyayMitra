/* =========================================================
   NYAYMITRA — MODEL API CLIENT
   (situation understanding + delay prediction)

   One module for the two model endpoints served by src/api.py:

     POST /understand-situation   free text -> intent, incident
                                  category, confidence, facts,
                                  missing information
     POST /predict-delay          case details -> predicted days
                                  to the next hearing AND days to
                                  disposal, in a single response

   The base URL comes from VITE_MODEL_API_URL (see .env.example).
   Nothing here hardcodes a host, and no page should ever build a
   model URL itself.

   Two conventions worth knowing:

   * Charset is spelled out on every request. The text may be
     English, Hindi or Marathi; `JSON.stringify` already emits
     UTF-8 bytes, and `charset=utf-8` keeps any intermediary from
     guessing a legacy encoding on the way in.

   * Errors carry a `kind` so the screen can distinguish a bad
     input from a rate limit from a dead server, instead of
     showing one generic "something went wrong".
   ========================================================= */

import { MODEL_API_BASE_URL } from "../api/config";

/* UTF-8 is stated explicitly: the text may be English, Hindi or
   Marathi, and no intermediary should be left to guess. */
const JSON_HEADERS: Record<string, string> = {
  Accept: "application/json",
  "Content-Type": "application/json; charset=utf-8",
};

/* =========================================================
   ERRORS
   ========================================================= */

/**
 * `kind` is what the screen actually branches on:
 *
 *   validation   400 / 422 — the input itself was rejected
 *   rate_limit   429 — too many requests, try again shortly
 *   server       500 — the API could not produce an answer
 *   unavailable  503 — the model module is not loaded
 *   network      fetch rejected — server down, CORS, offline
 *   unknown      anything else
 */
export type ModelApiErrorKind =
  | "validation"
  | "rate_limit"
  | "server"
  | "unavailable"
  | "network"
  | "unknown";

export class ModelApiError extends Error {
  readonly kind: ModelApiErrorKind;
  readonly status: number;

  constructor(message: string, kind: ModelApiErrorKind, status = 0) {
    super(message);
    this.name = "ModelApiError";
    this.kind = kind;
    this.status = status;
  }
}

function kindForStatus(status: number): ModelApiErrorKind {
  if (status === 400 || status === 422) return "validation";
  if (status === 429) return "rate_limit";
  if (status === 503) return "unavailable";
  if (status >= 500) return "server";
  return "unknown";
}

/**
 * FastAPI puts its message under `detail`; slowapi's rate-limit
 * handler uses `error`. Both are read, so a 429 never degrades
 * into "Request failed with status 429".
 */
function messageFromBody(body: unknown, fallback: string): string {
  if (body && typeof body === "object") {
    const record = body as Record<string, unknown>;

    for (const key of ["error", "detail", "message"]) {
      const value = record[key];

      if (typeof value === "string" && value.trim()) return value;

      /* FastAPI validation errors arrive as an array of objects. */
      if (Array.isArray(value) && value.length > 0) {
        const first = value[0] as Record<string, unknown>;
        const msg = first?.msg;

        if (typeof msg === "string" && msg.trim()) return msg;
      }
    }
  }

  return fallback;
}

async function post<T>(
  path: string,
  payload: unknown,
  fallbackMessage: string,
): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${MODEL_API_BASE_URL}${path}`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(payload),
    });
  } catch {
    /* fetch rejected: server not running, CORS blocked, offline. */
    throw new ModelApiError(
      "Could not reach the model service. Please check that it is running and try again.",
      "network",
    );
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    /* Non-JSON body (a proxy error page, an empty 500). The
       status code below still tells us what went wrong. */
    body = null;
  }

  if (!response.ok) {
    throw new ModelApiError(
      messageFromBody(body, fallbackMessage),
      kindForStatus(response.status),
      response.status,
    );
  }

  return body as T;
}

/* =========================================================
   1. TELL US WHAT HAPPENED
   POST /understand-situation   { "text": "..." }
   ========================================================= */

/** Exactly what the endpoint returns — no assumptions added here. */
export interface UnderstandSituationResponse {
  /** Lower-cased intent, or the literal "unclear". */
  intent: string;
  /** snake_case slug, null for CASE_QUESTION / FOLLOW_UP / unclear. */
  incident_category: string | null;
  /** "INC001"-style id, null exactly when incident_category is null. */
  category_id: string | null;
  confidence: number;
  /** Keys are the fact names from data/raw/incident_facts.json. */
  facts: Record<string, string> | null;
  missing_information: string[] | null;
  /** Set exactly when intent === "unclear". */
  message: string | null;
}

export async function understandSituation(
  text: string,
): Promise<UnderstandSituationResponse> {
  return post<UnderstandSituationResponse>(
    "/understand-situation",
    { text },
    "Could not understand this input.",
  );
}

/* =========================================================
   ADAPTER
   Wire shape -> the shape the Tell Us What Happened screen
   renders. This is the ONLY place that knows both sides, so a
   change to the API contract is absorbed here rather than
   spread across the page.
   ========================================================= */

export interface WhatHappenedView {
  /** intent === "unclear": ask for a rephrase, show no category. */
  isUnclear: boolean;
  intent: string;
  /** "Incident" / "Case question" / "Follow-up" / "Unclear". */
  intentLabel: string;
  /** 0.83 -> 83, for a percentage display. */
  confidencePercent: number;
  category: { slug: string; id: string } | null;
  facts: { key: string; value: string }[] | null;
  missingInformation: string[] | null;
  /** Only populated when isUnclear. */
  rephraseMessage: string | null;
}

const INTENT_LABELS: Record<string, string> = {
  incident: "Incident",
  case_question: "Case question",
  follow_up: "Follow-up",
  unclear: "Unclear",
};

/**
 * `incident_category`, `category_id`, `facts` and
 * `missing_information` are null in three different situations —
 * an unclear answer, and the two non-incident intents — and the
 * screen needs to tell them apart. `isUnclear` is the switch.
 */
export function toWhatHappenedView(
  response: UnderstandSituationResponse,
): WhatHappenedView {
  const isUnclear = response.intent === "unclear";
  const confidence = Number(response.confidence);

  const hasCategory =
    !isUnclear &&
    typeof response.incident_category === "string" &&
    response.incident_category.length > 0;

  const rawFacts = response.facts;
  const factEntries =
    rawFacts && typeof rawFacts === "object"
      ? Object.entries(rawFacts).filter(
          ([, value]) => value !== null && value !== undefined && value !== "",
        )
      : [];

  const missing = response.missing_information;

  return {
    isUnclear,
    intent: response.intent,
    intentLabel: INTENT_LABELS[response.intent] ?? response.intent,
    confidencePercent: Number.isFinite(confidence)
      ? Math.round(confidence * 100)
      : 0,
    category: hasCategory
      ? {
          slug: response.incident_category as string,
          id: response.category_id ?? "",
        }
      : null,
    facts: !isUnclear && factEntries.length > 0
      ? factEntries.map(([key, value]) => ({ key, value: String(value) }))
      : null,
    missingInformation:
      !isUnclear && Array.isArray(missing) && missing.length > 0
        ? missing
        : null,
    rephraseMessage: isUnclear
      ? response.message ??
        "I could not understand that confidently. Please rephrase your message or add a few more details about what happened."
      : null,
  };
}

/* =========================================================
   2. DELAY PREDICTION
   POST /predict-delay   -> BOTH predictions in one response
   ========================================================= */

export interface PredictDelayInput {
  case_type: string;
  court: string;
  district: string;
  state: string;
}

export interface PredictionExplanation {
  feature: string;
  contribution_days: number;
  text: string;
}

export interface PredictDelayResponse {
  /* Goal 2 — days to the next hearing. */
  predicted_next_hearing_days: number;
  predicted_delay_days: number;
  predicted_delay_lower: number;
  predicted_delay_upper: number;

  /* Goal 3 — days to disposal. `null` when the model is not
     trained; the screen must show "not available", never 0. */
  predicted_disposal_days: number | null;
  disposal_model_status: "trained" | "not_trained";
  disposal_explanation?: PredictionExplanation[];
  disposal_confidence_label?: string;
  disposal_model_version?: string;

  confidence_score: number;
  confidence_label: string;
  explanation: PredictionExplanation[];
  model_version: string;
}

export async function predictDelay(
  input: PredictDelayInput,
): Promise<PredictDelayResponse> {
  return post<PredictDelayResponse>(
    "/predict-delay",
    input,
    "Could not generate a prediction for this case.",
  );
}
