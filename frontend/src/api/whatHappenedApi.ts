import {
  TRANSLATION_API_BASE_URL,
  TRANSLATION_API_KEY,
  apiRequest,
} from "./config";

/* =========================================================
   NYAYMITRA — "WHAT HAPPENED?" CLIENT

   Wraps POST /api/what-happened on
   NyayMitra-feature-nlp-translation/translate_service.py

   Two modes share one envelope:

     incident  somebody describes something that happened and
               wants to understand it;
     case      somebody with a running case asks what happened
               or what to do next, answered only from the case
               record the client sends along with the question.

   Auth: Authorization: Bearer <API_KEY>, like every other
   endpoint on the NLP service.
   ========================================================= */

export type WhatHappenedLanguage = "en" | "hi" | "mr";

export type WhatHappenedMode = "incident" | "case";

/** The fields of `Case` the backend is allowed to read. The whole
 *  record is sent; this type documents what the answer may rest on.
 *  (No index signature on purpose — `Case` must stay assignable.) */
export interface WhatHappenedCaseContext {
  cnr_number?: string;
  case_type?: string;
  court_name?: string;
  current_case_stage?: string;
  next_hearing_date?: string;
  filing_date?: string;
  presiding_judge?: string;
  petitioner_name?: string;
  petitioner_advocate?: string;
  respondents_list?: string[];
  applied_act?: string;
  applied_section?: string;
  case_history_timeline?: {
    judge_title?: string;
    business_on_date?: string;
    hearing_date?: string;
    purpose_of_hearing?: string;
  }[];
}

export interface WhatHappenedRequest {
  mode: WhatHappenedMode;
  text: string;
  language: WhatHappenedLanguage;
  case_id?: string;
  conversation_id?: string;
  case_context?: WhatHappenedCaseContext | null;
}

/** The `/api/guidance` body, returned when the wording matched one
 *  of the fifty case stages in the existing guidance set. */
export interface WhatHappenedGuidance {
  matched?: boolean;
  stage?: string | null;
  urgency?: string | null;
  why?: string;
  what_to_do_next?: string;
  case_stage?: string;
  suggested_action?: string;
  related_terms?: { term: string; plain: string }[];
  candidates?: { stage: string; urgency: string }[];
  disclaimer?: string;
}

export interface WhatHappenedLegalTerm {
  term: string;
  plain: string;
  plain_hi?: string | null;
  plain_mr?: string | null;
}

export interface WhatHappenedResponse {
  mode: WhatHappenedMode;
  language: WhatHappenedLanguage;
  conversation_id: string;

  /** "Understood — you said yes." — set on a follow-up turn only. */
  acknowledgement: string;

  /* The five panels the screen renders. */
  summary: string;
  possible_issue: string;
  explanation: string;
  next_steps: string[];
  preserve_information: string[];
  follow_up_questions: string[];

  /* Case mode's grounded extras. Empty in incident mode. */
  case_facts: string[];
  record_gaps: string[];

  warnings: string[];

  time_sensitive: boolean;
  time_sensitivity_note: string;

  matched_stage: string | null;
  guidance: WhatHappenedGuidance | null;
  legal_terms: WhatHappenedLegalTerm[];

  disclaimer: string;

  /* What this turn asked, echoed back for the transcript. */
  user_text?: string;
}

function authHeaders(): HeadersInit {
  return {
    Authorization: `Bearer ${TRANSLATION_API_KEY}`,
  };
}

/**
 * One turn of the conversation. `conversation_id` is whatever the
 * previous response returned; leave it out to start a new thread.
 */
export async function askWhatHappened(
  request: WhatHappenedRequest,
): Promise<WhatHappenedResponse> {
  return apiRequest<WhatHappenedResponse>(
    TRANSLATION_API_BASE_URL,
    "/api/what-happened",
    {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify(request),
    },
  );
}
