import type { Role } from "./roles";

/* =========================================================
   AUTHENTICATED SESSION

   One login system detects whether the person is a
   USER, LAWYER, ADMIN or STAFF and stores that decision
   here.

   The session is persisted in localStorage so a page
   refresh does not throw the user back to the login
   screen during development.

   Later (JWT):
   - login() returns a real token from FastAPI
   - the token is stored instead of the mock session
   - the role comes from the decoded JWT claims
   ========================================================= */

export type VerificationStatus =
  | "PENDING"
  | "APPROVED"
  | "REJECTED";

export interface Session {
  userId: string;
  fullName: string;
  email: string;
  role: Role;

  /* Development only — replaced by the JWT later. */
  token: string;
  loginAt: string;

  /* Only present for LAWYER sessions. */
  lawyerId?: string;

  /* Only present for LAWYER sessions: PENDING / APPROVED /
     REJECTED, straight from the server's verification workflow.
     The client never sets or changes it — login just echoes back
     what the database says, so the UI can show "pending admin
     verification" truthfully. */
  verificationStatus?: VerificationStatus;
}

/* =========================================================
   STORAGE
   ========================================================= */

const SESSION_KEY = "nyaymitra.session";

export function saveSession(session: Session): void {
  try {
    localStorage.setItem(
      SESSION_KEY,
      JSON.stringify(session),
    );
  } catch {
    /* Storage unavailable — session stays in memory. */
  }
}

export function loadSession(): Session | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);

    if (!raw) {
      return null;
    }

    const parsed = JSON.parse(raw) as Partial<Session>;

    if (
      !parsed ||
      typeof parsed !== "object" ||
      typeof parsed.role !== "string" ||
      typeof parsed.email !== "string"
    ) {
      return null;
    }

    return parsed as Session;
  } catch {
    return null;
  }
}

export function clearSession(): void {
  try {
    localStorage.removeItem(SESSION_KEY);
  } catch {
    /* Nothing to clear. */
  }
}
