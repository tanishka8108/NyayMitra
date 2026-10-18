import {
  apiRequest as authenticatedApiRequest,
  LAWYER_API_BASE_URL,
} from "./config";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export interface Lawyer {
  lawyer_id: string;
  full_name: string;

  profile_photo?: string | null;
  profile_image?: string | null;

  gender?: string | null;
  date_of_birth?: string | null;

  years_of_experience?: number | null;

  enrollment_number?: string | null;
  registration_number?: string | null;
  bar_id_or_bar_code?: string | null;
  bar_council?: string | null;
  year_of_enrollment?: number | null;

  practice_areas?: string[] | null;
  courts_of_practice?: string[] | null;

  state?: string | null;
  district?: string | null;
  city?: string | null;

  office_address?: string | null;
  pincode?: string | null;

  professional_phone_number?: string | null;
  professional_email?: string | null;
  office_phone?: string | null;
  website?: string | null;
  preferred_contact_method?: string | null;

  education_qualifications?: string[] | null;
  languages_known?: string[] | null;

  working_office_hours?: string | null;
  professional_bio?: string | null;

  data_source?: string | null;
  profile_status?: string | null;

  created_at?: string | null;
  updated_at?: string | null;
}

export interface LawyerListResponse {
  count: number;
  total_count: number;
  page: number;
  limit: number;
  total_pages: number;
  lawyers: Lawyer[];
}

export interface LawyerSearchParams {
  name?: string;
  city?: string;
  district?: string;
  state?: string;
  practice_area?: string;
  min_experience?: number;
  max_experience?: number;
  page?: number;
  limit?: number;
}

export interface PracticeArea {
  practice_area_id: number;
  practice_area_name: string;
  description?: string | null;
}

export interface PracticeAreasResponse {
  count: number;
  practice_areas: PracticeArea[];
}

/* =========================================================
   GENERIC API REQUEST
   ========================================================= */

async function apiRequest<T>(
  endpoint: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(
    `${API_BASE_URL}${endpoint}`,
    {
      ...options,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...(options?.headers || {}),
      },
    },
  );

  if (!response.ok) {
    let message =
      `API request failed with status ${response.status}.`;

    try {
      const errorData: unknown =
        await response.json();

      if (
        errorData &&
        typeof errorData === "object" &&
        "detail" in errorData &&
        typeof errorData.detail === "string"
      ) {
        message = errorData.detail;
      }
    } catch {
      // Keep default HTTP error message.
    }

    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

/* =========================================================
   GET LAWYERS
   ========================================================= */

export async function getLawyers(
  params: LawyerSearchParams = {},
): Promise<LawyerListResponse> {
  const query = new URLSearchParams();

  if (params.name?.trim()) {
    query.set("name", params.name.trim());
  }

  if (params.city?.trim()) {
    query.set("city", params.city.trim());
  }

  if (params.district?.trim()) {
    query.set("district", params.district.trim());
  }

  if (params.state?.trim()) {
    query.set("state", params.state.trim());
  }

  if (params.practice_area?.trim()) {
    query.set(
      "practice_area",
      params.practice_area.trim(),
    );
  }

  if (params.min_experience !== undefined) {
    query.set(
      "min_experience",
      String(params.min_experience),
    );
  }

  if (params.max_experience !== undefined) {
    query.set(
      "max_experience",
      String(params.max_experience),
    );
  }

  if (params.page !== undefined) {
    query.set(
      "page",
      String(params.page),
    );
  }

  if (params.limit !== undefined) {
    query.set(
      "limit",
      String(params.limit),
    );
  }

  const queryString = query.toString();

  return apiRequest<LawyerListResponse>(
    `/api/lawyers${
      queryString
        ? `?${queryString}`
        : ""
    }`,
  );
}

/* =========================================================
   GET ONE LAWYER
   ========================================================= */

export async function getLawyerById(
  lawyerId: string,
): Promise<Lawyer> {
  const id = lawyerId.trim();

  if (!id) {
    throw new Error(
      "Lawyer ID is required.",
    );
  }

  const record = await apiRequest<Lawyer>(
    `/api/lawyers/${encodeURIComponent(id)}`,
  );

  const verification = getLawyerVerification(
    record.lawyer_id || id,
  );

  return applyProfileEdits(
    id,
    verification
      ? { ...record, profile_status: verification }
      : record,
  );
}

/* =========================================================
   PROFILE EDITS

   The lawyer API has no write endpoint, so corrections the
   advocate makes to their own record are held here rather
   than sent anywhere. They are layered over whatever the API
   returns on every read, which means the dashboard's
   completeness figure, the profile page and the Find Lawyer
   listing all see the same edited values without any of them
   knowing an edit happened.

   Only the advocate's own fields are covered — registration
   and verification status are not something a lawyer can
   amend about themselves, and are deliberately absent.
   ========================================================= */

const PROFILE_EDITS_KEY =
  "nyaymitra.lawyer.profileEdits";

export type EditableProfileField =
  | "professional_bio"
  | "working_office_hours"
  | "city"
  | "district"
  | "state"
  | "pincode"
  | "office_address"
  | "professional_email"
  | "professional_phone_number"
  | "office_phone"
  | "preferred_contact_method"
  | "website";

export type EditableProfileList =
  | "practice_areas"
  | "courts_of_practice"
  | "languages_known"
  | "education_qualifications";

type ScalarFieldDef = {
  key: EditableProfileField;
  label: string;
  /** Rendered as a textarea rather than an input. */
  lines?: number;
  type?: string;
};

type ListFieldDef = {
  key: EditableProfileList;
  label: string;
};

/** Scalar fields an advocate may correct, with the label the form shows. */
const SCALAR_FIELDS: readonly ScalarFieldDef[] = [
  { key: "professional_bio", label: "Professional bio", lines: 4 },
  { key: "working_office_hours", label: "Working office hours" },
  { key: "professional_email", label: "Professional email", type: "email" },
  { key: "professional_phone_number", label: "Professional phone" },
  { key: "office_phone", label: "Office phone" },
  { key: "preferred_contact_method", label: "Preferred contact method" },
  { key: "website", label: "Website", type: "url" },
  { key: "city", label: "City" },
  { key: "district", label: "District" },
  { key: "state", label: "State" },
  { key: "pincode", label: "Pincode" },
  { key: "office_address", label: "Office address", lines: 3 },
];

/** List fields, edited as one entry per line. */
const LIST_FIELDS: readonly ListFieldDef[] = [
  { key: "practice_areas", label: "Practice areas" },
  { key: "courts_of_practice", label: "Courts of practice" },
  { key: "languages_known", label: "Languages known" },
  { key: "education_qualifications", label: "Education qualifications" },
];

export const PROFILE_SCALAR_FIELDS = SCALAR_FIELDS;
export const PROFILE_LIST_FIELDS = LIST_FIELDS;

export type ProfilePatch =
  Partial<Record<EditableProfileField, string>> &
    Partial<Record<EditableProfileList, string[]>>;

/**
 * A record's current values for the editable fields, ready to be
 * used as the starting point of an edit.
 */
export function editableSnapshot(source: Lawyer): ProfilePatch {
  const patch: ProfilePatch = {};

  // Split across two narrowed views: a write through the union of
  // both key kinds would have to satisfy `string & string[]`.
  const scalars = patch as Partial<
    Record<EditableProfileField, string>
  >;
  for (const field of SCALAR_FIELDS) {
    scalars[field.key] = source[field.key] ?? "";
  }

  const lists = patch as Partial<
    Record<EditableProfileList, string[]>
  >;
  for (const field of LIST_FIELDS) {
    lists[field.key] = [...(source[field.key] ?? [])];
  }

  return patch;
}

/**
 * The edit form holds every field as text — list values are one
 * entry per line — so a single `Record<string, string>` is the
 * whole draft and there is no point where a scalar and a list
 * have to share an index type.
 */
export type ProfileDraft = Partial<
  Record<EditableProfileField | EditableProfileList, string>
>;

export function toProfileDraft(
  patch: ProfilePatch,
): ProfileDraft {
  const draft = {} as ProfileDraft;

  const scalars = patch as Partial<
    Record<EditableProfileField, string>
  >;
  for (const field of SCALAR_FIELDS) {
    draft[field.key] = scalars[field.key] ?? "";
  }

  const lists = patch as Partial<
    Record<EditableProfileList, string[]>
  >;
  for (const field of LIST_FIELDS) {
    draft[field.key] = (lists[field.key] ?? []).join("\n");
  }

  return draft;
}

/** Split the form back into the shape the record stores. */
export function fromProfileDraft(
  draft: ProfileDraft,
): ProfilePatch {
  const patch: ProfilePatch = {};

  const scalars = patch as Partial<
    Record<EditableProfileField, string>
  >;
  for (const field of SCALAR_FIELDS) {
    scalars[field.key] = draft[field.key] ?? "";
  }

  const lists = patch as Partial<
    Record<EditableProfileList, string[]>
  >;
  for (const field of LIST_FIELDS) {
    lists[field.key] = (draft[field.key] ?? "")
      .split("\n")
      .map((entry) => entry.trim())
      .filter(Boolean);
  }

  return patch;
}

type ProfileEdits = Record<string, ProfilePatch>;

function readProfileEdits(): ProfileEdits {
  try {
    const raw =
      window.localStorage.getItem(PROFILE_EDITS_KEY);

    if (!raw) return {};

    const parsed: unknown = JSON.parse(raw);

    return parsed && typeof parsed === "object"
      ? (parsed as ProfileEdits)
      : {};
  } catch {
    /* Unreadable or unavailable — behave as if nothing was edited. */
    return {};
  }
}

/** Read back the corrections held for one lawyer. */
export function readProfileEditsFor(
  lawyerId: string,
): ProfilePatch {
  return readProfileEdits()[lawyerId.trim()] ?? {};
}

/**
 * Store corrections for one lawyer, replacing any held
 * before. Values are written as given: an emptied field
 * stores an empty string, which then reads back as empty
 * rather than falling through to the API's older value.
 */
export function saveProfileEdits(
  lawyerId: string,
  patch: ProfilePatch,
): void {
  const id = lawyerId.trim();
  if (!id) return;

  try {
    const all = readProfileEdits();
    all[id] = patch;
    window.localStorage.setItem(
      PROFILE_EDITS_KEY,
      JSON.stringify(all),
    );
  } catch {
    /* Private mode or a full quota — the edit simply does not persist. */
  }
}

function applyProfileEdits(
  lawyerId: string,
  record: Lawyer,
): Lawyer {
  const patch = readProfileEdits()[lawyerId];

  if (!patch) return record;

  return { ...record, ...patch };
}

/* =========================================================
   VERIFICATION

   The other half of the record an advocate cannot touch about
   themselves: whether the platform has checked their papers.
   Set by the administrator — or by a staff member holding the
   lawyers.verify authority — and read back by every screen
   that shows a status, so Manage Lawyers, Lawyer Records and
   the directory itself cannot disagree about it.

   Held here rather than on the profile-edit overlay for the
   reason that overlay states: it is not the lawyer's to edit.
   ========================================================= */

const VERIFICATION_KEY = "nyaymitra.lawyer.verification";

export type VerificationState = "Verified" | "Pending" | "Rejected";

export const VERIFICATION_STATES: readonly VerificationState[] = [
  "Verified",
  "Pending",
  "Rejected",
];

type VerificationMap = Record<string, VerificationState>;

let verificationMemory: VerificationMap | null = null;
let verificationStorageUsable = true;

function readVerifications(): VerificationMap {
  if (verificationStorageUsable) {
    try {
      const raw = window.localStorage.getItem(VERIFICATION_KEY);

      if (raw) {
        const parsed = JSON.parse(raw) as VerificationMap;

        if (parsed && typeof parsed === "object") return parsed;
      }
    } catch {
      verificationStorageUsable = false;
    }
  }

  verificationMemory ??= {};
  return verificationMemory;
}

function writeVerifications(next: VerificationMap): void {
  verificationMemory = next;

  if (!verificationStorageUsable) return;

  try {
    window.localStorage.setItem(
      VERIFICATION_KEY,
      JSON.stringify(next),
    );
  } catch {
    verificationStorageUsable = false;
  }
}

/** Null when nobody has ruled on this advocate yet. */
export function getLawyerVerification(
  lawyerId: string,
): VerificationState | null {
  const id = lawyerId.trim();

  if (!id) return null;

  return readVerifications()[id] ?? null;
}

export function setLawyerVerification(
  lawyerId: string,
  state: VerificationState,
): void {
  const id = lawyerId.trim();
  if (!id) return;

  const all = readVerifications();

  if (state === "Pending") {
    /* Back to "nobody has ruled" rather than a stored default. */
    delete all[id];
  } else {
    all[id] = state;
  }

  writeVerifications(all);
}

/** How many advocates an admin or staff member has ruled on. */
export function countDecidedVerifications(): number {
  return Object.keys(readVerifications()).length;
}


interface OwnLawyerProfileResponse {
  lawyer_id: string;
  full_name: string;
  email: string;
  license_id: string;
  practice_areas: string[];
  verification_status: "PENDING" | "APPROVED" | "REJECTED";
  bar_council?: string | null;
  years_of_experience?: number | null;
  professional_phone_number?: string | null;
  professional_bio?: string | null;
  created_at?: string | null;
}

export async function getOwnLawyerProfile(): Promise<Lawyer> {
  const profile =
    await authenticatedApiRequest<OwnLawyerProfileResponse>(
      LAWYER_API_BASE_URL,
      "/api/auth/lawyer/profile",
    );

  const record: Lawyer = {
    lawyer_id: profile.lawyer_id,
    full_name: profile.full_name,
    enrollment_number: profile.license_id,
    registration_number: profile.license_id,
    bar_id_or_bar_code: profile.license_id,
    bar_council: profile.bar_council,
    practice_areas: profile.practice_areas,
    years_of_experience: profile.years_of_experience,
    professional_email: profile.email,
    professional_phone_number: profile.professional_phone_number,
    professional_bio: profile.professional_bio,
    profile_status: profile.verification_status,
    created_at: profile.created_at,
  };

  return applyProfileEdits(profile.lawyer_id, record);
}

/* =========================================================
   GET PRACTICE AREAS
   ========================================================= */

export async function getPracticeAreas(): Promise<PracticeAreasResponse> {
  return apiRequest<PracticeAreasResponse>(
    "/api/practice-areas",
  );
}