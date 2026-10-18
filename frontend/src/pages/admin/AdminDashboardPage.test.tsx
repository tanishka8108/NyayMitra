import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AdminDashboardPage from "./AdminDashboardPage";

import { saveSession } from "../../auth/session";
import type { Session } from "../../auth/session";

/* =========================================================
   ADMIN DASHBOARD — rulings that reach the server.

   The bug this file exists for: the dashboard's approve and
   reject buttons used to write to a browser-local store, so
   an "Verified" pill here changed nothing on the server and
   no lawyer ever became verified through it. This screen now
   reads /api/admin/lawyers and PATCHes every ruling there.

   A stubbed `fetch` stands in for FastAPI (the admin endpoints,
   plus the per-row detail calls the Records screen resolves).
   What is under test:

   - rows arrive from the admin registration service with the
     stored status, and the counts read the same list;
   - the uploaded papers' viewer only appears where a document
     exists — and where none does, the row says so;
   - clicking Verify PATCHes {verification_status: APPROVED}
     with the session token and repaints from the answer;
   - a refusal (403) keeps the old status standing and puts
     the server's sentence on screen.

   The wire contract is adminApi.test.ts; the authorization
   rules are NyayMitra-feature-lawyer-api/tests/
   test_verification_admin.py.
   ========================================================= */

const SESSION: Session = {
  userId: "1",
  fullName: "Demo Admin",
  email: "admin@nyaymitra.in",
  role: "ADMIN",
  token: "admin-token",
  loginAt: "2026-10-04T00:00:00.000Z",
};

interface StubResponse {
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
}

function jsonResponse(
  body: unknown,
  ok = true,
  status = 200,
): StubResponse {
  return { ok, status, json: async () => body };
}

type ServerStatus = "PENDING" | "APPROVED" | "REJECTED";

interface StoredRegistration {
  lawyer_id: string;
  user_id: number;
  full_name: string;
  email: string;
  license_id: string;
  practice_areas: string[];
  verification_status: ServerStatus;
  verified_by: number | null;
  verified_at: string | null;
  created_at: string;
  is_demo: boolean;
  bar_council: string | null;
  years_of_experience: number | null;
  professional_phone_number: string | null;
  professional_bio: string | null;
  document: {
    filename: string;
    mime_type: string;
    size_bytes: number;
    sha256: string;
    uploaded_at: string;
  } | null;
}

const LABELS: Record<ServerStatus, string> = {
  APPROVED: "Verified",
  PENDING: "Pending",
  REJECTED: "Rejected",
};

/* Mutable server state + a switch for the refusal test. */
let stored: StoredRegistration[];
let patchError: string | null;

function resetServer(): void {
  stored = [
    {
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
    },
    {
      lawyer_id: "LAWYER_0003",
      user_id: 7,
      full_name: "Adv. Rohan Deshmukh",
      email: "rohan@example.com",
      license_id: "MH/9999/2020",
      practice_areas: ["Criminal"],
      verification_status: "APPROVED",
      verified_by: 1,
      verified_at: "2026-09-30 12:00:00",
      created_at: "2026-09-01 09:00:00",
      is_demo: true,
      bar_council: "Bombay Bar Council",
      years_of_experience: 17,
      professional_phone_number: null,
      professional_bio: null,
      document: null,
    },
  ];

  patchError = null;
}

const fetchMock = vi.fn(
  async (
    input: RequestInfo | URL,
    init?: RequestInit,
  ): Promise<StubResponse> => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();

    if (method === "PATCH" && url.includes("/api/admin/lawyers/")) {
      if (patchError) {
        return jsonResponse({ detail: patchError }, false, 403);
      }

      const id = url.slice(url.lastIndexOf("/") + 1);
      const body = JSON.parse(String(init?.body)) as {
        verification_status: ServerStatus;
      };

      const target = stored.find((row) => row.lawyer_id === id);
      if (!target) {
        return jsonResponse({ detail: "Lawyer not found" }, false, 404);
      }

      target.verification_status = body.verification_status;
      target.verified_by =
        body.verification_status === "PENDING" ? null : 1;
      return jsonResponse(target);
    }

    if (method === "GET" && url.includes("/api/admin/lawyers")) {
      return jsonResponse({
        count: stored.length,
        total_count: stored.length,
        page: 1,
        limit: 12,
        total_pages: 1,
        lawyers: stored,
      });
    }

    if (method === "GET" && url.includes("/api/lawyers/")) {
      const id = url.slice(url.lastIndexOf("/") + 1);
      const target = stored.find((row) => row.lawyer_id === id);
      if (!target) {
        return jsonResponse({ detail: "Lawyer not found" }, false, 404);
      }

      return jsonResponse({
        lawyer_id: target.lawyer_id,
        full_name: target.full_name,
        bar_council: target.bar_council,
        years_of_experience: target.years_of_experience,
        professional_email: target.email,
        profile_status: LABELS[target.verification_status],
      });
    }

    return jsonResponse({ detail: `Unhandled ${method} ${url}` }, false, 500);
  },
);

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  saveSession(SESSION);
  resetServer();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  window.localStorage.clear();
});

function renderDashboard(): void {
  render(
    <AdminDashboardPage
      session={SESSION}
      onSignOut={() => {}}
      onNavigate={() => {}}
    />,
  );
}

async function openManageLawyers(): Promise<HTMLElement> {
  fireEvent.click(
    screen.getByRole("button", { name: /Manage Lawyers/ }),
  );

  await screen.findByText("Adv. Queue Demo");

  return document.querySelector(".section-rows") as HTMLElement;
}

function patchCalls(): [string, RequestInit][] {
  return fetchMock.mock.calls
    .filter(
      ([url, init]) =>
        String(url).includes("/api/admin/lawyers/") &&
        (init as RequestInit | undefined)?.method === "PATCH",
    )
    .map(([url, init]) => [String(url), init as RequestInit]);
}

describe("the registrations list", () => {
  it("renders the stored status, the papers and the counts", async () => {
    renderDashboard();

    const rows = await openManageLawyers();

    /* The list is read with the admin's session token. */
    const listCall = fetchMock.mock.calls.find(([url]) =>
      String(url).includes("/api/admin/lawyers?"),
    );
    expect(listCall).toBeDefined();
    const headers = (listCall![1] as RequestInit).headers as Record<
      string,
      string
    >;
    expect(headers.Authorization).toBe("Bearer admin-token");

    /* Each row shows the status the server stores… */
    const pendingRow = screen
      .getByText("Adv. Queue Demo")
      .closest("li") as HTMLElement;
    const approvedRow = screen
      .getByText("Adv. Rohan Deshmukh")
      .closest("li") as HTMLElement;

    expect(within(pendingRow).getByText("Pending")).toBeInTheDocument();
    expect(within(approvedRow).getByText("Verified")).toBeInTheDocument();

    /* …the viewer appears only where papers were uploaded… */
    expect(
      within(pendingRow).getByRole("button", { name: "View document" }),
    ).toBeInTheDocument();
    expect(
      within(approvedRow).queryByRole("button", {
        name: "View document",
      }),
    ).not.toBeInTheDocument();
    expect(within(approvedRow).getByText("No document")).toBeInTheDocument();

    /* …and the counts come from that same list. */
    expect(
      screen.getByText("AWAITING REVIEW").parentElement,
    ).toHaveTextContent("1");
    expect(screen.getByText("VERIFIED").parentElement).toHaveTextContent(
      "1",
    );

    expect(rows).toBeTruthy();
    expect(patchCalls()).toHaveLength(0);
  });
});

describe("ruling on a registration", () => {
  it("PATCHes the server and repaints from its answer", async () => {
    renderDashboard();

    const rows = await openManageLawyers();

    /* The pending registration is the first row — the one to rule on. */
    fireEvent.click(
      within(rows).getAllByRole("button", { name: "Verify" })[0],
    );

    const pendingRow = screen
      .getByText("Adv. Queue Demo")
      .closest("li") as HTMLElement;

    await within(pendingRow).findByText("Verified");

    /* The PATCH carries exactly the ruling, with the session token. */
    const calls = patchCalls();
    expect(calls).toHaveLength(1);
    expect(calls[0][0]).toContain("/api/admin/lawyers/LAWYER_0007");
    expect(JSON.parse(String(calls[0][1].body))).toEqual({
      verification_status: "APPROVED",
    });
    const headers = calls[0][1].headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer admin-token");

    /* The counts follow the stored status. */
    expect(
      screen.getByText("AWAITING REVIEW").parentElement,
    ).toHaveTextContent("0");
    expect(screen.getByText("VERIFIED").parentElement).toHaveTextContent(
      "2",
    );
  });

  it("keeps the old status and shows the reason when refused", async () => {
    patchError = "Admin session required";

    renderDashboard();

    const rows = await openManageLawyers();

    fireEvent.click(
      within(rows).getAllByRole("button", { name: "Reject" })[0],
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Admin session required",
    );

    /* Nothing changed on screen, because nothing changed on the server. */
    const pendingRow = screen
      .getByText("Adv. Queue Demo")
      .closest("li") as HTMLElement;
    expect(within(pendingRow).getByText("Pending")).toBeInTheDocument();

    await waitFor(() => {
      expect(
        within(pendingRow).getByRole("button", { name: "Reject" }),
      ).toBeEnabled();
    });
  });
});
