/* =========================================================
   AUTHORITY API

   The administrator holds every authority and delegates a
   subset to staff. Which subset is decided here; the admin
   screen only toggles flags, and the staff dashboard reads
   them back.

   Mock-backed like the other pending endpoints — flip
   VITE_AUTHORITY_MODE to "api" and reimplement the three
   functions below once FastAPI exposes /authorities.

   The catalogue is the staff dashboard's sections, plus
   lawyer verification — a grant maps onto a real screen
   instead of a flag nothing reads.
   ========================================================= */

export interface Authority {
  id: string;
  label: string;
  description: string;
  /* Where this sits on the screen. Grouped rather than listed
     flat because "Update case files" and "Submit reports" are
     unrelated decisions — the category is what lets the admin
     grant a whole area of work and then refine it. */
  category: AuthorityCategory;
}

export type AuthorityCategory =
  | "Case work"
  | "Reviews & reporting"
  | "Communications";

export const AUTHORITY_CATEGORIES: readonly AuthorityCategory[] = [
  "Case work",
  "Reviews & reporting",
  "Communications",
];

export const AUTHORITY_CATALOG: Authority[] = [
  {
    id: "cases.update",
    label: "Update case files",
    description:
      "Edit case records, attach documents and mark filing status.",
    category: "Case work",
  },
  {
    id: "hearings.view",
    label: "View hearings",
    description:
      "See upcoming hearings, cause lists and court activities.",
    category: "Case work",
  },
  {
    id: "documents.process",
    label: "Process documents",
    description:
      "Upload and process court orders through OCR and PDF pipelines.",
    category: "Case work",
  },
  {
    id: "lawyers.verify",
    label: "Verify lawyer accounts",
    description:
      "Confirm or reject an advocate's registration papers.",
    category: "Reviews & reporting",
  },
  {
    id: "reports.submit",
    label: "Submit reports",
    description:
      "File daily activity summaries to the administrator.",
    category: "Reviews & reporting",
  },
  {
    id: "messages.send",
    label: "Message users and lawyers",
    description:
      "Hold conversations with citizens and advocates on assigned matters.",
    category: "Communications",
  },
];

export const AUTHORITY_IDS: string[] = AUTHORITY_CATALOG.map(
  (authority) => authority.id,
);

/** The catalogue in the order the screen groups it. */
export function authoritiesByCategory(): Array<{
  category: AuthorityCategory;
  authorities: Authority[];
}> {
  return AUTHORITY_CATEGORIES.map((category) => ({
    category,
    authorities: AUTHORITY_CATALOG.filter(
      (authority) => authority.category === category,
    ),
  })).filter((group) => group.authorities.length > 0);
}

/**
 * What a newly issued staff account starts with.
 *
 * Deliberately small: an account is issued with the work it was
 * created to do, and the rest is granted from Access & Roles.
 */
export const DEFAULT_AUTHORITIES: string[] = [
  "cases.update",
  "hearings.view",
  "messages.send",
];

/* =========================================================
   STAFF WORK ASSIGNMENT

   Who does what, decided once here rather than inferred from
   the authorities somebody happens to hold — the two are
   related but not the same, and the admin needs both: the
   assignment says what the person is for, the authorities say
   what the platform lets them do about it.

   Each entry names the authorities that work implies, so the
   Access screen can offer it as a starting point without
   quietly granting anything on its own.
   ========================================================= */

export type StaffWorkId =
  | "cases"
  | "hearings"
  | "documents"
  | "verification"
  | "messages"
  | "reports";

export interface StaffWork {
  id: StaffWorkId;
  label: string;
  description: string;
  /* Suggested — never applied automatically. */
  authorities: string[];
}

export const STAFF_WORK: readonly StaffWork[] = [
  {
    id: "cases",
    label: "Case records",
    description: "Keeps filings, parties and stage updates accurate.",
    authorities: ["cases.update"],
  },
  {
    id: "hearings",
    label: "Hearings & cause lists",
    description: "Tracks listed dates, adjournments and court activity.",
    authorities: ["hearings.view", "cases.update"],
  },
  {
    id: "documents",
    label: "Document processing",
    description: "Reads court orders and files papers against matters.",
    authorities: ["documents.process"],
  },
  {
    id: "verification",
    label: "Lawyer verification",
    description: "Checks registration papers before advocates go live.",
    authorities: ["lawyers.verify"],
  },
  {
    id: "messages",
    label: "Communications",
    description: "Answers citizens and advocates on assigned matters.",
    authorities: ["messages.send"],
  },
  {
    id: "reports",
    label: "Operational reports",
    description: "Compiles daily summaries for the administrator.",
    authorities: ["reports.submit"],
  },
];

export const STAFF_WORK_IDS: string[] = STAFF_WORK.map(
  (work) => work.id,
);

const WORK_KEY = "nyaymitra.staff.work.v1";

type WorkMap = Record<string, StaffWorkId>;

let workMemory: WorkMap | null = null;
let workStorageUsable = true;

function readWork(): WorkMap {
  if (workStorageUsable) {
    try {
      const raw = window.localStorage.getItem(WORK_KEY);

      if (raw) {
        const parsed = JSON.parse(raw) as WorkMap;

        if (parsed && typeof parsed === "object") return parsed;
      }
    } catch {
      workStorageUsable = false;
    }
  }

  workMemory ??= {};
  return workMemory;
}

function writeWork(next: WorkMap): void {
  workMemory = next;

  if (!workStorageUsable) return;

  try {
    window.localStorage.setItem(WORK_KEY, JSON.stringify(next));
  } catch {
    workStorageUsable = false;
  }
}

/** Null until the admin has assigned something. */
export function getWorkFor(
  staffUserId: string,
): StaffWorkId | null {
  const id = staffUserId.trim();
  if (!id) return null;

  return readWork()[id] ?? null;
}

export function setWorkFor(
  staffUserId: string,
  /* An empty string clears the assignment. */
  workId: StaffWorkId | "",
): void {
  const id = staffUserId.trim();
  if (!id) return;

  const all = readWork();

  if (workId === "") {
    delete all[id];
  } else {
    all[id] = workId;
  }

  writeWork(all);
}

/** The entry itself, for a label. */
export function workById(
  workId: StaffWorkId | null,
): StaffWork | null {
  if (!workId) return null;

  return STAFF_WORK.find((work) => work.id === workId) ?? null;
}

/* =========================================================
   STORE

   Same shape as chatApi: localStorage first, an in-memory
   copy behind it so a blocked quota degrades instead of
   dropping every grant the admin has set.
   ========================================================= */

const STORAGE_KEY = "nyaymitra.authorities.v1";

type GrantMap = Record<string, string[]>;

let memory: GrantMap | null = null;
let storageUsable = true;

function readGrants(): GrantMap {
  if (storageUsable) {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as GrantMap;
        if (parsed && typeof parsed === "object") return parsed;
      }
    } catch {
      storageUsable = false;
    }
  }

  memory ??= {};
  return memory;
}

function writeGrants(next: GrantMap): void {
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

/**
 * Authorities held by one staff member. Unknown accounts fall back to
 * DEFAULT_AUTHORITIES so an account issued before this existed is not
 * silently locked out of everything.
 */
export function getAuthoritiesFor(staffUserId: string): string[] {
  const grants = readGrants();
  const stored = grants[staffUserId];

  if (Array.isArray(stored)) return stored;

  return [...DEFAULT_AUTHORITIES];
}

export function hasAuthority(
  staffUserId: string,
  authorityId: string,
): boolean {
  return getAuthoritiesFor(staffUserId).includes(authorityId);
}

/**
 * Grant or revoke one authority for one staff member.
 *
 * Returns the resulting list so callers can render the new state without
 * a second read.
 */
export function setAuthorityFor(
  staffUserId: string,
  authorityId: string,
  on: boolean,
): string[] {
  if (!AUTHORITY_IDS.includes(authorityId)) {
    throw new Error(`Unknown authority: ${authorityId}`);
  }

  const grants = readGrants();
  const current = new Set(getAuthoritiesFor(staffUserId));

  if (on) {
    current.add(authorityId);
  } else {
    current.delete(authorityId);
  }

  const next = [...current];
  writeGrants({ ...grants, [staffUserId]: next });

  return next;
}

/**
 * Replace a staff member's authorities wholesale — used by the "grant all" /
 * "revoke all" controls so the admin does not have to click through five rows.
 */
export function setAuthoritiesFor(
  staffUserId: string,
  authorityIds: string[],
): string[] {
  const unknown = authorityIds.filter(
    (id) => !AUTHORITY_IDS.includes(id),
  );

  if (unknown.length > 0) {
    throw new Error(`Unknown authorities: ${unknown.join(", ")}`);
  }

  const grants = readGrants();
  const next = [...new Set(authorityIds)];

  writeGrants({ ...grants, [staffUserId]: next });

  return next;
}

/**
 * The administrator holds everything. Exposed so the admin screen can show
 * its own row as locked-on rather than as just another grantable list.
 */
export const ADMIN_AUTHORITIES: readonly string[] = AUTHORITY_IDS;
