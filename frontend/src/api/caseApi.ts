/* =========================================================
   NYAYMITRA — CASE STORE

   `mockCases` stays exactly as it is: the fixture, immutable
   and shared. This module adds the one thing a static array
   cannot do — let a citizen save a matter they looked up by
   CNR — without forcing every existing reader to change how
   it reads.

   Nothing in this module creates a court case. NyayMitra
   tracks real cases; it never files them.

   Only user-saved cases are persisted. The seeds come from
   `mockCases` on every read, so fixing a fixture value (a
   stale hearing date, a renamed party) takes effect
   immediately instead of being trapped behind whatever was
   copied into localStorage the first time the app ran.

   Synchronous, like the auth and authority stores: the
   screens that read cases render on the first pass and
   there is no request to wait for.
   ========================================================= */

import { mockCases } from "../mocks/cases";
import type {
  Case,
  CaseDataSource,
  CaseMetrics,
} from "../types/case";
import { LAWYER_API_BASE_URL, apiRequest } from "./config";

const STORAGE_KEY = "nyaymitra.cases.added.v1";

let memory: Case[] | null = null;
let storageUsable = true;

function read(): Case[] {
  if (storageUsable) {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);

      if (raw) {
        const parsed = JSON.parse(raw) as unknown;

        if (Array.isArray(parsed)) return parsed as Case[];
      }
    } catch {
      storageUsable = false;
    }
  }

  memory ??= [];
  return memory;
}

function write(next: Case[]): void {
  memory = next;

  if (!storageUsable) return;

  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    storageUsable = false;
  }
}

/* =========================================================
   QUERIES
   ========================================================= */

/** Every case on the platform: the ones this account saved,
 *  then the seeded fixture. */
export function getCases(): Case[] {
  return [...read(), ...mockCases];
}

export function getCase(cnr: string): Case | null {
  return (
    getCases().find((item) => item.cnr_number === cnr) ?? null
  );
}

/** Cases owned by one account — the My Cases filter. */
export function getCasesForUser(userId: string): Case[] {
  return getCases().filter(
    (item) => item.owner_user_id === userId,
  );
}

/** Cases handled by one advocate — the Active Cases filter. */
export function getCasesForLawyer(lawyerId: string): Case[] {
  return getCases().filter(
    (item) => item.handling_lawyer_id === lawyerId,
  );
}

/* The stages a matter reaches when it is over. There is no `status`
   field on Case, so the stage is the only thing that can answer
   "is this still live?" — and it is worth being generous here: a
   word the fixture does not use leaves the case open rather than
   hiding it from the citizen tracking it. */
const CLOSED_STAGE =
  /(closed|concluded|disposed|dismissed|withdrawn|acquitted|settled|disposed of)/i;

export function isOngoing(item: Case): boolean {
  return !CLOSED_STAGE.test(item.current_case_stage ?? "");
}

/**
 * The cases a screen offering a per-case action should list — delay
 * prediction and the timeline both skip anything already finished,
 * because the question they answer only applies while the matter runs.
 */
export function getOngoingCasesForUser(userId: string): Case[] {
  return getCasesForUser(userId).filter(isOngoing);
}

/* =========================================================
   SAVING A CASE TO MY CASES

   Nothing in this section fabricates a court case. The record
   arrives from the case service (`lookupCaseByCnr`) already
   complete, and saving only claims it for one account — a tag
   on an existing record, never a new one. There is no "file a
   new case" path: NyayMitra tracks real cases, it never
   creates them.
   ========================================================= */

/** Is this CNR already among the cases this account saved? */
export function isSavedForUser(
  cnr: string,
  userId: string,
): boolean {
  return getCasesForUser(userId).some(
    (item) => item.cnr_number === cnr,
  );
}

/**
 * Save a looked-up case to My Cases.
 *
 * - The record itself is untouched apart from `owner_user_id`:
 *   every field (CNR, parties, dates, timeline) stays exactly
 *   as the service reported it.
 * - Idempotent: saving a CNR this account already has changes
 *   nothing, so the list never grows duplicates — whether the
 *   copy came from an earlier save or from the seeded fixture.
 * - Existing saved cases are never rewritten; this only ever
 *   appends one record.
 *
 * Returns the saved record (or the already-saved copy).
 */
export function saveCaseForUser(
  record: Case,
  userId: string,
): Case {
  if (isSavedForUser(record.cnr_number, userId)) {
    return (
      getCasesForUser(userId).find(
        (item) => item.cnr_number === record.cnr_number,
      ) ?? record
    );
  }

  const saved: Case = { ...record, owner_user_id: userId };

  write([saved, ...read()]);

  return saved;
}

/**
 * Re-read after a fixture or store change. Exported so a screen
 * that has just saved a case can rebuild its list without
 * re-running the whole component tree.
 */
export function resetCases(): void {
  memory = null;
  storageUsable = true;

  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    storageUsable = false;
  }
}

/* =========================================================
   LOOKING A CASE UP BY CNR — the case service

   The store above is this browser's own bookkeeping. A CNR search
   is not: it asks the case service (NyayMitra-feature-lawyer-api)
   for one record, and the answer comes back shaped like every
   other `Case` on the screen, so the card and the detail view
   work on it without knowing where it came from.

   What the service returns is development data — a normalised
   copy of records captured manually from eCourts — and its
   provenance rides along on `data_source`, so the screen can
   say plainly what it is showing.
   ========================================================= */

type ServiceCase = Omit<
  Case,
  "owner_user_id" | "handling_lawyer_id" | "calculated_metrics"
> & {
  owner_user_id?: string;
  handling_lawyer_id?: string;
  calculated_metrics?: CaseMetrics;
};

interface CaseLookupResponse {
  success: boolean;
  case: ServiceCase;
  data_source: CaseDataSource;
}

/**
 * Fetch one case by CNR.
 *
 * Throws with the service's own message when it can answer: a
 * malformed CNR is a 400 saying what a CNR looks like, an unknown
 * one a 404 naming only that number — both written for whoever
 * typed it. When the service cannot be reached at all, the
 * browser's fetch error surfaces instead, and the caller says the
 * service could not be reached rather than pretending the number
 * was tested.
 */
export async function lookupCaseByCnr(
  cnr: string,
  userId: string,
): Promise<Case> {
  const payload = await apiRequest<CaseLookupResponse>(
    LAWYER_API_BASE_URL,
    `/api/cases/cnr/${encodeURIComponent(cnr.trim())}`,
  );

  const record = payload.case;

  return {
    ...record,
    owner_user_id: record.owner_user_id || userId,
    handling_lawyer_id: record.handling_lawyer_id || "",
    respondents_list: record.respondents_list ?? [],
    case_history_timeline: record.case_history_timeline ?? [],
    timeline: record.timeline ?? [],
    orders: record.orders ?? [],
    data_source: payload.data_source,
    calculated_metrics: record.calculated_metrics ?? {
      respondent_count: (record.respondents_list ?? []).length,
      total_case_age_days: 0,
      total_hearings_scheduled: (record.case_history_timeline ?? []).length,
      current_stage_duration_days: 0,
    },
  };
}
