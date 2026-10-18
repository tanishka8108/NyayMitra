import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  login,
  register,
  registerLawyerAccount,
  uploadLawyerDocument,
} from "./authApi";

/* =========================================================
   AUTH API — the wire contract in both directions.

   A stubbed `fetch` stands in for FastAPI, so what is under test is
   what this module sends (and what it makes of the answer):

   - login sends ONLY { email, password } — never the door/role the
     user picked; the server decides the role;
   - register sends the four snake_case fields — never a role;
   - registerLawyerAccount sends the licence + profile fields —
     never a role, never a verification_status;
   - uploadLawyerDocument posts multipart with the Bearer token;
   - verification_status from the server lands on Session as
     verificationStatus (never invented client-side);
   - server error `detail` strings reach the caller as the thrown
     message (what the login/register forms display);
   - user_id arrives as a number and is normalized to the string
     Session.userId the rest of the app expects.

   The real endpoints are covered by
   NyayMitra-feature-lawyer-api/tests.
   ========================================================= */

interface StubResponse {
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
}

function jsonResponse(body: unknown, ok = true, status = 200): StubResponse {
  return { ok, status, json: async () => body };
}

const AUTH_BODY = {
  access_token: "server-token",
  token_type: "bearer",
  user: {
    user_id: 42,
    full_name: "Test Citizen",
    email: "citizen@example.com",
    role: "USER",
    is_demo: false,
    lawyer_id: null,
  },
};

const fetchMock = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

function lastBody(): Record<string, unknown> {
  const [, init] = fetchMock.mock.calls[
    fetchMock.mock.calls.length - 1
  ] as [string, RequestInit];
  return JSON.parse(String(init.body)) as Record<string, unknown>;
}

function lastUrl(): string {
  const calls = fetchMock.mock.calls;
  return String(calls[calls.length - 1][0]);
}

describe("login", () => {
  it("posts email + password only — the chosen door is never sent", async () => {
    fetchMock.mockResolvedValue(jsonResponse(AUTH_BODY));

    const session = await login({
      role: "ADMIN",
      identifier: "  Citizen@Example.COM ",
      password: "password123",
    });

    expect(lastUrl()).toMatch(/\/api\/auth\/login$/);
    expect(lastBody()).toEqual({
      email: "  Citizen@Example.COM ",
      password: "password123",
    });
    expect(lastBody()).not.toHaveProperty("role");

    /* Normalized to the Session shape: string id, server token. */
    expect(session.userId).toBe("42");
    expect(session.role).toBe("USER");
    expect(session.token).toBe("server-token");
    expect(session.fullName).toBe("Test Citizen");
    expect(session.lawyerId).toBeUndefined();
  });

  it("surfaces the backend's generic 401 detail", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { detail: "Invalid email or password." },
        false,
        401,
      ),
    );

    await expect(
      login({
        role: "USER",
        identifier: "nobody@example.com",
        password: "wrong",
      }),
    ).rejects.toThrow("Invalid email or password.");
  });

  it("falls back to a status message when the body has no detail", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(null, false, 500),
    );

    await expect(
      login({
        role: "USER",
        identifier: "citizen@example.com",
        password: "x",
      }),
    ).rejects.toThrow(/status 500/);
  });
});

describe("register", () => {
  it("posts the four snake_case fields — never a role", async () => {
    fetchMock.mockResolvedValue(jsonResponse(AUTH_BODY, true, 201));

    const session = await register({
      fullName: "New Citizen",
      email: "new@example.com",
      password: "password123",
      passwordConfirmation: "password123",
    });

    expect(lastUrl()).toMatch(/\/api\/auth\/register$/);
    expect(lastBody()).toEqual({
      full_name: "New Citizen",
      email: "new@example.com",
      password: "password123",
      password_confirmation: "password123",
    });
    expect(lastBody()).not.toHaveProperty("role");

    expect(session.userId).toBe("42");
    expect(session.role).toBe("USER");
    expect(session.token).toBe("server-token");
  });

  it("surfaces a 409 duplicate-email detail", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { detail: "An account with this email already exists." },
        false,
        409,
      ),
    );

    await expect(
      register({
        fullName: "New Citizen",
        email: "new@example.com",
        password: "password123",
        passwordConfirmation: "password123",
      }),
    ).rejects.toThrow("An account with this email already exists.");
  });
});

/* =========================================================
   VERIFICATION STATUS — echoed, never invented
   ========================================================= */

describe("verification status", () => {
  it("keeps the server's verification_status on a lawyer session", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        ...AUTH_BODY,
        user: {
          ...AUTH_BODY.user,
          role: "LAWYER",
          lawyer_id: "LAWYER_0007",
          verification_status: "PENDING",
        },
      }),
    );

    const session = await login({
      role: "LAWYER",
      identifier: "advocate@example.com",
      password: "password123",
    });

    expect(session.verificationStatus).toBe("PENDING");
    expect(session.lawyerId).toBe("LAWYER_0007");
  });

  it("leaves it undefined when the server sends none (citizen)", async () => {
    fetchMock.mockResolvedValue(jsonResponse(AUTH_BODY));

    const session = await login({
      role: "USER",
      identifier: "citizen@example.com",
      password: "password123",
    });

    expect(session.verificationStatus).toBeUndefined();
  });
});

/* =========================================================
   REGISTER AS LAWYER — part 1 (JSON) + part 2 (document)
   ========================================================= */

describe("registerLawyerAccount", () => {
  it("posts licence and profile fields — never a role or status", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          ...AUTH_BODY,
          user: {
            ...AUTH_BODY.user,
            role: "LAWYER",
            lawyer_id: "LAWYER_0007",
            verification_status: "PENDING",
          },
        },
        true,
        201,
      ),
    );

    const session = await registerLawyerAccount({
      fullName: "Test Advocate",
      email: "advocate@example.com",
      password: "password123",
      passwordConfirmation: "password123",
      licenseId: "MAH/1234/2020",
      practiceAreas: "Criminal Law, Family Law",
      barCouncil: "Bar Council of Maharashtra",
      yearsOfExperience: 7,
      phone: "+91 98765 43210",
      bio: "High Court advocate.",
    });

    expect(lastUrl()).toMatch(
      /\/api\/auth\/register\/lawyer$/,
    );

    const body = lastBody();
    expect(body).toEqual({
      full_name: "Test Advocate",
      email: "advocate@example.com",
      password: "password123",
      password_confirmation: "password123",
      license_id: "MAH/1234/2020",
      practice_areas: ["Criminal Law", "Family Law"],
      bar_council: "Bar Council of Maharashtra",
      years_of_experience: 7,
      professional_phone_number: "+91 98765 43210",
      professional_bio: "High Court advocate.",
    });
    expect(body).not.toHaveProperty("role");
    expect(body).not.toHaveProperty("verification_status");

    /* The PENDING status comes back from the server, not from us. */
    expect(session.verificationStatus).toBe("PENDING");
    expect(session.role).toBe("LAWYER");
  });

  it("omits optional profile fields that were left empty", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(AUTH_BODY, true, 201),
    );

    await registerLawyerAccount({
      fullName: "Test Advocate",
      email: "advocate@example.com",
      password: "password123",
      passwordConfirmation: "password123",
      licenseId: "MAH/1234/2020",
      practiceAreas: "Civil Law",
      barCouncil: "   ",
      phone: "",
      bio: "",
    });

    const body = lastBody();
    expect(body).not.toHaveProperty("bar_council");
    expect(body).not.toHaveProperty("professional_phone_number");
    expect(body).not.toHaveProperty("professional_bio");
    expect(body.practice_areas).toEqual(["Civil Law"]);
  });
});

describe("uploadLawyerDocument", () => {
  const PDF_FILE = new File(
    ["%PDF-1.4 fake bytes"],
    "licence.pdf",
    { type: "application/pdf" },
  );

  it("posts multipart with the Bearer token and no forced content-type", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}, true, 201));

    await uploadLawyerDocument("lawyer-token", PDF_FILE);

    expect(lastUrl()).toMatch(
      /\/api\/auth\/lawyer\/verification-document$/,
    );

    const [, init] = fetchMock.mock.calls[
      fetchMock.mock.calls.length - 1
    ] as [string, RequestInit];

    expect(init.body).toBeInstanceOf(FormData);

    const form = init.body as FormData;
    expect((form.get("file") as File).name).toBe(
      "licence.pdf",
    );

    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe(
      "Bearer lawyer-token",
    );
    /* The browser must set the multipart boundary itself. */
    expect(headers["Content-Type"]).toBeUndefined();
  });

  it("surfaces the server's upload error detail", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          detail:
            "File too large. Maximum allowed size is 10 MB.",
        },
        false,
        400,
      ),
    );

    await expect(
      uploadLawyerDocument("lawyer-token", PDF_FILE),
    ).rejects.toThrow(
      "File too large. Maximum allowed size is 10 MB.",
    );
  });
});
