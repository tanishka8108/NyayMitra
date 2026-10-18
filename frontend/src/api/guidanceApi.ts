/* =========================================================
   NYAYMITRA — "WHAT SHOULD I DO NOW"

   Whatever somebody says about their situation is matched
   against the fifty case stages the guidance set covers, and
   the stage it lands on says what that stage calls for.

   Nothing here is a model's opinion about a particular
   incident. `urgency` is the band the matched stage carries
   in the guidance set — a lookup, not a prediction — and the
   screen labels it as such until the incident-urgency model
   arrives.
   ========================================================= */

import {
  TRANSLATION_API_BASE_URL,
  TRANSLATION_API_KEY,
} from "./config";

export interface GuidanceTerm {
  term: string;
  plain: string;
}

export interface GuidanceCandidate {
  stage: string;
  urgency: string;
}

export interface GuidanceResult {
  matched: boolean;
  stage: string | null;
  urgency: string | null;
  why: string;
  what_to_do_next: string;
  related_terms: GuidanceTerm[];
  candidates: GuidanceCandidate[];
  disclaimer: string;
}

/** The situation, read against the stages the set covers. */
export async function getGuidance(
  text: string,
): Promise<GuidanceResult> {
  const response = await fetch(
    `${TRANSLATION_API_BASE_URL}/api/guidance`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${TRANSLATION_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ text }),
    },
  );

  if (!response.ok) {
    let detail = "Your description could not be read.";

    try {
      const payload: unknown = await response.json();

      if (
        payload &&
        typeof payload === "object" &&
        "detail" in payload &&
        typeof payload.detail === "string"
      ) {
        detail = payload.detail;
      }
    } catch {
      /* Not JSON — keep the fallback. */
    }

    throw new Error(`${detail} (status ${response.status})`);
  }

  return (await response.json()) as GuidanceResult;
}
