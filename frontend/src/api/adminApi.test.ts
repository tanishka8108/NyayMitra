import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  fetchVerificationDocument,
  getAdminLawyers,
  setAdminVerification,
  toLabel,
  toStatus,
} from "./adminApi";

import { saveSession } from "../auth/session";

/* =========================================================
   ADMIN API — the verification wire contract.

   A stubbed `fetch` stands in for FastAPI. What is under
   test:

   - the Bearer token comes from the saved session — the
     module never invents identity headers;
   - the list reads /api/admin/lawyers with the same
     envelope every listing in this app speaks;
   - a ruling PATCHes exactly {verification_status} — the
     request model on the server forbids any other field;
   - the server's `detail` reaches the caller as the thrown
     message (what the dashboard shows in its alert);
   - the document bytes ride a token-authenticated fetch
     that apiRequest could not make (it parses JSON);
   - the two vocabularies — PENDING/APPROVED/REJECTED as
     stored, Pending/Verified/Rejected as shown — map
     round-trip at this boundary.

   The real endpoints are covered by
   NyayMitra-feature-lawyer-api/tests/test_verification_admin.py
   and test_lawyer_documents.py.
   ========================================================= */

interface StubResponse {
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
  blob: () => Promise<Blob>;
}

function jsonResponse(
  body: unknown,
  ok = true,
  status = 200,
): StubResponse {
  return {
    ok,
    status,
    json: async () => body,
    blob: async () => new Blob(),
  };
}

function bytesResponse(
  bytes: BlobPart[],
  type: string,
): StubResponse {
  return {
    ok: true,
    status: 200,
    json: async () => ({}),
    blob: async () => new Blob(bytes, { type }),
  };
}

const fetchMock = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);

  /* The session token is what config.apiRequest attaches — so the
     header under test is the real one the app would send. */
  saveSession({
    userId: "1",
    fullName: "Demo Admin",
    email: "admin@nyaymitra.in",
    role: "ADMIN",
    token: "admin-token",
    loginAt: "2026-10-04T00:00:00.000Z",
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  window.localStorage.clear();
});

function lastCall(): [string, RequestInit] {
  const calls = fetchMock.mock.calls;
  return calls[calls.length - 1] as [string, RequestInit];
}

function authHeader(init: RequestInit): unknown {
  return (init.headers as Record<string, string>)?.Authorization;
}

const PENDING_REGISTRATION = {
  lawyer_id: "LAWYER_0007",
  user_id: 42,
  full_name: "Adv. Queue Demo",
  email: "queue.demo@example.com",
  license_id: "MH/1234/2026",
  practice_areas: ["Civil"],
  verification_status: "PENDING",
  verified_by: null,
  verified_at: null,
  created_at: "2026-10-01 09:00:00",
  is_demo: false,
  bar_council: "Bombay Bar Council",
  years_of_experience: 8,
  professional_phone_number: null,
  professional_bio: null,
  document: {
    filename: "license.pdf",
    mime_type: "application/pdf",
    size_bytes: 2048,
    sha256: "abc123",
    uploaded_at: "2026-10-01 09:05:00",
  },
};

const LIST_ENVELOPE = {
  count: 1,
  total_count: 3,
  page: 1,
  limit: 12,
  total_pages: 1,
  lawyers: [PENDING_REGISTRATION],
};

describe("getAdminLawyers", () => {
  it("reads the registrations with the session token", async () => {
    fetchMock.mockResolvedValue(jsonResponse(LIST_ENVELOPE));

    const page = await getAdminLawyers({ page: 1, limit: 12 });

    const [url, init] = lastCall();
    expect(String(url)).toMatch(
      /\/api\/admin\/lawyers\?page=1&limit=12$/,
    );
    expect(authHeader(init)).toBe("Bearer admin-token");

    expect(page.total_count).toBe(3);
    expect(page.lawyers[0].verification_status).toBe("PENDING");
    expect(page.lawyers[0].document?.filename).toBe("license.pdf");
  });

  it("filters the approvals queue by status", async () => {
    fetchMock.mockResolvedValue(jsonResponse(LIST_ENVELOPE));

    await getAdminLawyers({ status: "PENDING" });

    const [url] = lastCall();
    expect(String(url)).toMatch(/status=PENDING/);
  });
});

describe("setAdminVerification", () => {
  it("sends exactly the ruling and reads the stored answer", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        ...PENDING_REGISTRATION,
        verification_status: "APPROVED",
        verified_by: 1,
      }),
    );

    const updated = await setAdminVerification("LAWYER_0007", "APPROVED");

    const [url, init] = lastCall();
    expect(String(url)).toMatch(/\/api\/admin\/lawyers\/LAWYER_0007$/);
    expect(init.method).toBe("PATCH");
    expect(authHeader(init)).toBe("Bearer admin-token");
    expect(JSON.parse(String(init.body))).toEqual({
      verification_status: "APPROVED",
    });

    expect(updated.verification_status).toBe("APPROVED");
    expect(updated.verified_by).toBe(1);
  });

  it("surfaces the server's refusal as the thrown message", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: "Admin session required" }, false, 403),
    );

    await expect(
      setAdminVerification("LAWYER_0007", "APPROVED"),
    ).rejects.toThrow("Admin session required");
  });
});

describe("fetchVerificationDocument", () => {
  it("asks for the bytes with the admin token", async () => {
    fetchMock.mockResolvedValue(
      bytesResponse(["%PDF-1.7"], "application/pdf"),
    );

    const blob = await fetchVerificationDocument("LAWYER_0007");

    const [url, init] = lastCall();
    expect(String(url)).toMatch(
      /\/api\/admin\/lawyers\/LAWYER_0007\/document$/,
    );
    expect(authHeader(init)).toBe("Bearer admin-token");
    expect(blob.type).toBe("application/pdf");
  });

  it("reports 'nothing uploaded' in the server's own words", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: "Document not found" }, false, 404),
    );

    await expect(
      fetchVerificationDocument("LAWYER_0007"),
    ).rejects.toThrow("Document not found");
  });
});

describe("the two status vocabularies", () => {
  it("maps what is stored onto the words the pills say", () => {
    expect(toLabel("APPROVED")).toBe("Verified");
    expect(toLabel("PENDING")).toBe("Pending");
    expect(toLabel("REJECTED")).toBe("Rejected");
  });

  it("maps the pill words back onto what the server stores", () => {
    expect(toStatus("Verified")).toBe("APPROVED");
    expect(toStatus("Pending")).toBe("PENDING");
    expect(toStatus("Rejected")).toBe("REJECTED");
  });
});
