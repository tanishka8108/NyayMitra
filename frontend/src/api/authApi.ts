import type { Role } from "../auth/roles";
import type { Session, VerificationStatus } from "../auth/session";
import { isDeactivated } from "./accountApi";
import { LAWYER_API_BASE_URL } from "./config";

/* =========================================================
   NYAYMITRA — AUTH API

   One login system detects the role and returns a session.

   MODES
   - "api" (DEFAULT): talks to the FastAPI service — the real
     system: /api/auth/register, /api/auth/login.
   - "mock": offline demo, DEVELOPMENT ONLY. The demo credentials
     live behind `import.meta.env.DEV`, so `vite build` (production)
     contains no passwords at all.

   BACKEND CONTRACT — implemented in
   NyayMitra-feature-lawyer-api/auth/routes.py:

     POST /api/auth/register   201
       { full_name, email, password, password_confirmation }
       -> { access_token, token_type, user }

       The client may NOT choose a role: the request model has no
       role field and rejects unknown fields (422), and the server
       assigns USER.

     POST /api/auth/register/lawyer   201
       { full_name, email, password, password_confirmation,
         license_id, practice_areas, bar_council?, ... }
       -> session, user.role = LAWYER,
          user.verification_status = "PENDING" (server-assigned)

       The document is attached by the follow-up multipart call
       below, sent as part of the same submission.

     POST /api/auth/lawyer/verification-document  201 / 400 / 409
       multipart/form-data, field "file" — PDF/JPEG/PNG, max 10 MB.
       (Bearer token) replaces any previously uploaded copy.

     POST /api/auth/login      200 / 401
       { email, password }
       -> { access_token, token_type, user }
          user: { user_id, full_name, email, role, is_demo,
                  lawyer_id, verification_status }

       Unknown email and wrong password share one generic 401
       message, so accounts cannot be enumerated.

     POST /api/auth/logout     (Authorization: Bearer <token>)
     GET  /api/auth/me         (Authorization: Bearer <token>)

   The session token is attached to every lawyer-service request by
   apiRequest() in config.ts.
   ========================================================= */

/* =========================================================
   USE MOCK?
   ========================================================= */

const USE_MOCK =
  (import.meta.env.VITE_AUTH_MODE || "api") === "mock";

/*
 * Exported so pages can adjust their copy (demo panel, input hints)
 * without duplicating the switch logic.
 */
export const IS_MOCK_AUTH = USE_MOCK;

/* =========================================================
   LOGIN INPUT
   ========================================================= */

export interface LoginInput {
  /* The door the person entered from (see LoginPage). It is NOT
     sent to the server — the role always comes from the database. */
  role: Role;
  identifier: string;
  password: string;
}

/* =========================================================
   REGISTER INPUT — citizen self-registration
   ========================================================= */

export interface RegisterInput {
  fullName: string;
  email: string;
  password: string;
  passwordConfirmation: string;
}

/* =========================================================
   LAWYER REGISTER INPUT — advocate self-registration

   The licence document travels in a separate multipart call
   (uploadLawyerDocument) right after the JSON registration —
   one user submission, two requests, retryable per step.
   ========================================================= */

export interface LawyerRegisterInput {
  fullName: string;
  email: string;
  password: string;
  passwordConfirmation: string;
  licenseId: string;
  /* Free text, comma-separated in the form; cleaned server-side. */
  practiceAreas: string;
  barCouncil?: string;
  yearsOfExperience?: number | null;
  phone?: string;
  bio?: string;
}

/* =========================================================
   MOCK ACCOUNTS — DEVELOPMENT ONLY

   Demo credentials for the capstone demo. `import.meta.env.DEV` is
   inlined as `false` by `vite build`, so production bundles carry an
   empty list — demo credentials are never shipped to users.

   STAFF accounts are issued by ADMIN — see issueStaffAccount().
   ========================================================= */

interface MockAccount {
  userId: string;
  fullName: string;
  email: string;
  password: string;
  role: Role;
  lawyerId?: string;
  verificationStatus?: VerificationStatus;
}

const MOCK_ACCOUNTS: MockAccount[] = import.meta.env.DEV
  ? [
      {
        userId: "USER_0001",
        fullName: "Asha Verma",
        email: "asha@example.com",
        password: "user123",
        role: "USER",
      },
      {
        userId: "LAWYER_0003",
        fullName: "Adv. Rohan Deshmukh",
        email: "rohan@example.com",
        password: "lawyer123",
        role: "LAWYER",
        lawyerId: "LAWYER_0003",
        /* The seeded demo advocate is APPROVED, like in the
           database — so mock mode shows the same state the API
           would return. */
        verificationStatus: "APPROVED",
      },
      {
        userId: "ADMIN_0001",
        fullName: "Site Administrator",
        email: "admin@nyaymitra.in",
        password: "admin123",
        role: "ADMIN",
      },
      {
        userId: "STAFF_0001",
        fullName: "Kavya Iyer",
        email: "kavya@nyaymitra.in",
        password: "staff123",
        role: "STAFF",
      },
    ]
  : [];

/* =========================================================
   MOCK: ISSUE A STAFF ACCOUNT

   Staff login goes through the admin login:

   Admin signs in → Admin dashboard → Staff management →
   issue credentials → staff member can now sign in.

   In mock mode the seeded staff account above always
   exists so the demo works out of the box, but this
   function documents the intended flow for the real API.
   ========================================================= */

export interface StaffInvite {
  fullName: string;
  email: string;
  password: string;
}

export function issueStaffAccount(
  invite: StaffInvite,
  issuedBy: Session,
): MockAccount {
  if (issuedBy.role !== "ADMIN") {
    throw new Error(
      "Only an administrator can issue staff accounts.",
    );
  }

  const account: MockAccount = {
    userId: `STAFF_${String(MOCK_ACCOUNTS.length).padStart(4, "0")}`,
    fullName: invite.fullName.trim(),
    email: invite.email.trim().toLowerCase(),
    password: invite.password,
    role: "STAFF",
  };

  MOCK_ACCOUNTS.push(account);

  return account;
}

/* =========================================================
   MOCK LOGIN
   ========================================================= */

function mockLogin(input: LoginInput): Session {
  const identifier = input.identifier.trim().toLowerCase();

  if (!identifier) {
    throw new Error("Enter your email or user ID.");
  }

  if (!input.password) {
    throw new Error("Enter your password.");
  }

  const account = MOCK_ACCOUNTS.find(
    (candidate) =>
      candidate.email.toLowerCase() === identifier ||
      candidate.userId.toLowerCase() === identifier,
  );

  if (!account) {
    throw new Error(
      "No account found for that email or user ID.",
    );
  }

  /*
   * ROLE MISMATCH
   *
   * The login page already knows which door the person
   * entered through. Signing in through the wrong door
   * is rejected here — this is the "one login system
   * detects the role" rule.
   */
  if (account.role !== input.role) {
    throw new Error(
      `This account is a ${account.role} account. ` +
        `Please sign in through the ${account.role} door.`,
    );
  }

  if (account.password !== input.password) {
    throw new Error("Incorrect password.");
  }

  return {
    userId: account.userId,
    fullName: account.fullName,
    email: account.email,
    role: account.role,
    token: `mock-token-${account.userId}`,
    loginAt: new Date().toISOString(),
    lawyerId: account.lawyerId,
    verificationStatus: account.verificationStatus,
  };
}

/* =========================================================
   REAL API — shared by login and register
   ========================================================= */

interface AuthApiResponse {
  access_token: string;
  token_type: string;
  user: {
    user_id: number;
    full_name: string;
    email: string;
    role: Role;
    is_demo?: boolean;
    lawyer_id?: string | null;
    verification_status?: VerificationStatus | null;
  };
}

async function postForSession(
  path: string,
  body: Record<string, unknown>,
): Promise<Session> {
  const response = await fetch(`${LAWYER_API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    let message =
      `Authentication failed with status ${response.status}.`;

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

  const data = (await response.json()) as AuthApiResponse;

  return {
    userId: String(data.user.user_id),
    fullName: data.user.full_name,
    email: data.user.email,
    role: data.user.role,
    token: data.access_token,
    loginAt: new Date().toISOString(),
    lawyerId: data.user.lawyer_id ?? undefined,
    verificationStatus: data.user.verification_status ?? undefined,
  };
}

/* =========================================================
   PUBLIC: LOGIN
   ========================================================= */

export async function login(
  input: LoginInput,
): Promise<Session> {
  /*
   * DEACTIVATED ACCOUNTS
   *
   * Checked before either path runs, mock or API. An account the
   * administrator switched off never gets as far as its password —
   * and saying which it is costs nothing, because somebody who has
   * been switched off is exactly the person who needs to know.
   */
  const deactivated = DEMO_ACCOUNTS.find(
    (account) =>
      account.email.trim().toLowerCase() ===
      input.identifier.trim().toLowerCase(),
  );

  if (deactivated && isDeactivated(deactivated.userId)) {
    throw new Error(
      "This account has been deactivated. " +
        "Contact the administrator to have it reactivated.",
    );
  }

  if (USE_MOCK) {
    /* Simulated network delay so the UI shows its
       loading state the same way it will with FastAPI. */
    await new Promise((resolve) =>
      setTimeout(resolve, 450),
    );

    return mockLogin(input);
  }

  /*
   * Only email + password cross the wire. The door the user picked
   * (input.role) is deliberately NOT sent: the server decides the
   * role from the database, never from the client.
   */

const session = await postForSession("/api/auth/login", {
  email: input.identifier,
  password: input.password,
});

if (session.role !== input.role) {
  const roleNames: Record<Role, string> = {
    USER: "Citizen",
    LAWYER: "Lawyer",
    ADMIN: "Admin",
    STAFF: "Staff",
  };

  throw new Error(
    `This account is registered as ${roleNames[session.role]}. ` +
      `Please sign in through the ${roleNames[session.role]} login option.`,
  );
}

return session;

}

/* =========================================================
   PUBLIC: REGISTER (citizen self-registration)

   Creates a USER account and returns an active session — the new
   user is signed in straight away. There is no role field: the
   server would reject one.
   ========================================================= */

export async function register(
  input: RegisterInput,
): Promise<Session> {
  if (USE_MOCK) {
    await new Promise((resolve) =>
      setTimeout(resolve, 450),
    );

    const account: MockAccount = {
      userId: `USER_${String(MOCK_ACCOUNTS.length + 1).padStart(4, "0")}`,
      fullName: input.fullName.trim(),
      email: input.email.trim().toLowerCase(),
      password: input.password,
      role: "USER",
    };

    MOCK_ACCOUNTS.push(account);

    return {
      userId: account.userId,
      fullName: account.fullName,
      email: account.email,
      role: account.role,
      token: `mock-token-${account.userId}`,
      loginAt: new Date().toISOString(),
    };
  }

  return postForSession("/api/auth/register", {
    full_name: input.fullName,
    email: input.email,
    password: input.password,
    password_confirmation: input.passwordConfirmation,
  });
}

/* =========================================================
   PUBLIC: REGISTER (lawyer self-registration, part 1 of 2)

   Creates the LAWYER account — always PENDING, the server
   decides — and returns a session whose token the document
   upload reuses. The JSON body never carries a role, a status,
   or the file: those live in their own places (server rules and
   the multipart call below).

   The page sends both calls as one submission; splitting them
   keeps a flaky upload from destroying the entered form data —
   see uploadLawyerDocument for the retry half.
   ========================================================= */

export async function registerLawyerAccount(
  input: LawyerRegisterInput,
): Promise<Session> {
  if (USE_MOCK) {
    await new Promise((resolve) =>
      setTimeout(resolve, 450),
    );

    const account: MockAccount = {
      userId: `LAWYER_${String(MOCK_ACCOUNTS.length + 1).padStart(4, "0")}`,
      fullName: input.fullName.trim(),
      email: input.email.trim().toLowerCase(),
      password: input.password,
      role: "LAWYER",
      lawyerId: `LAWYER_${String(MOCK_ACCOUNTS.length + 1).padStart(4, "0")}`,
      /* Mock registrations are never pre-approved — same rule as
         the API, so the pending screen is exercised in demo mode. */
      verificationStatus: "PENDING",
    };

    MOCK_ACCOUNTS.push(account);

    return {
      userId: account.userId,
      fullName: account.fullName,
      email: account.email,
      role: account.role,
      token: `mock-token-${account.userId}`,
      loginAt: new Date().toISOString(),
      lawyerId: account.lawyerId,
      verificationStatus: account.verificationStatus,
    };
  }

  const body: Record<string, unknown> = {
    full_name: input.fullName,
    email: input.email,
    password: input.password,
    password_confirmation: input.passwordConfirmation,
    license_id: input.licenseId,
    practice_areas: input.practiceAreas
      .split(/[,;]/)
      .map((area) => area.trim())
      .filter(Boolean),
  };

  /* Optional profile fields — only sent when filled, so an empty
     form field never becomes an empty string row. */
  if (input.barCouncil?.trim()) {
    body.bar_council = input.barCouncil.trim();
  }
  if (
    input.yearsOfExperience !== null &&
    input.yearsOfExperience !== undefined &&
    !Number.isNaN(input.yearsOfExperience)
  ) {
    body.years_of_experience = input.yearsOfExperience;
  }
  if (input.phone?.trim()) {
    body.professional_phone_number = input.phone.trim();
  }
  if (input.bio?.trim()) {
    body.professional_bio = input.bio.trim();
  }

  return postForSession("/api/auth/register/lawyer", body);
}

/* =========================================================
   PUBLIC: UPLOAD THE LICENCE DOCUMENT (lawyer registration,
   part 2 of 2)

   multipart/form-data with the Bearer token the registration
   step just returned — the endpoint accepts only the caller's
   own LAWYER session, and the server re-validates type and
   size on the bytes themselves.
   ========================================================= */

async function readErrorMessage(
  response: Response,
): Promise<string> {
  try {
    const errorData: unknown = await response.json();

    if (
      errorData &&
      typeof errorData === "object" &&
      "detail" in errorData &&
      typeof errorData.detail === "string"
    ) {
      return errorData.detail;
    }
  } catch {
    /* Keep the default HTTP message. */
  }

  return `Upload failed with status ${response.status}.`;
}

export async function uploadLawyerDocument(
  token: string,
  document: File,
): Promise<void> {
  if (USE_MOCK) {
    await new Promise((resolve) =>
      setTimeout(resolve, 450),
    );
    /* Nothing stored in demo mode — the API is the real thing. */
    return;
  }

  const form = new FormData();
  form.append("file", document, document.name);

  const response = await fetch(
    `${LAWYER_API_BASE_URL}/api/auth/lawyer/verification-document`,
    {
      method: "POST",
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: form,
    },
  );

  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }
}

/* =========================================================
   DEMO CREDENTIALS (shown on the login page in mock mode)

   Empty in production builds (see MOCK_ACCOUNTS above), so demo
   credentials are never part of a shipped frontend bundle.
   ========================================================= */

export const DEMO_ACCOUNTS = MOCK_ACCOUNTS.map(
  (account) => ({
    userId: account.userId,
    role: account.role,
    fullName: account.fullName,
    email: account.email,
    password: account.password,
  }),
);
