import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  deleteConversation,
  getConversation,
  listAvailableLawyers,
  listConversations,
  sendMessage,
  startConversation,
} from "./chatApi";

import { saveSession } from "../auth/session";

/* =========================================================
   CHAT API — the Phase 3 wire contract.

   A stubbed `fetch` stands in for FastAPI (API mode is the
   default; no VITE_CHAT_MODE stubbing needed). What is under
   test:

   - the Bearer token comes from the saved session — the module
     never invents identity headers;
   - USER threads come from /api/chat/conversations, LAWYER
     threads from /api/chat/lawyer/conversations;
   - startConversation sends the *target* id only (lawyer_id for
     a citizen, user_id for an advocate) — never a sender/user
     identity of our own, which the server would refuse (422)
     anyway;
   - the snake_case wire shape maps onto the ChatConversation /
     ChatMessage types every page already speaks;
   - server `detail` strings reach the caller as the thrown
     message (what the inbox displays);
   - deletion is unavailable server-side, so the API refuses it
     cleanly instead of pretending.

   The real endpoints are covered by
   NyayMitra-feature-lawyer-api/tests/test_chat_api.py.
   ========================================================= */

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

const SERVER_THREAD = {
  id: 5,
  user_id: 7,
  user_name: "Test Citizen",
  lawyer_id: "LAWYER_0003",
  lawyer_name: "Adv. Rohan Deshmukh",
  case_cnr: "MHPU210000042026",
  created_at: "2026-10-01 10:00:00",
  updated_at: "2026-10-01 10:05:00",
  messages: [
    {
      id: 11,
      sender_id: 7,
      sender_role: "USER",
      message: "Namaste.",
      created_at: "2026-10-01 10:00:00",
    },
    {
      id: 12,
      sender_id: 9,
      sender_role: "LAWYER",
      message: "How can I help?",
      created_at: "2026-10-01 10:05:00",
    },
  ],
};

const fetchMock = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);

  /* The session token is what config.apiRequest attaches — so the
     header under test is the real one the app would send. */
  saveSession({
    userId: "7",
    fullName: "Test Citizen",
    email: "citizen@example.com",
    role: "USER",
    token: "test-token",
    loginAt: "2026-10-01T00:00:00.000Z",
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

function lastBody(): Record<string, unknown> {
  const [, init] = lastCall();
  return JSON.parse(String(init.body)) as Record<string, unknown>;
}

function authHeader(init: RequestInit): unknown {
  return (init.headers as Record<string, string>)?.Authorization;
}

const citizenParty = {
  id: "7",
  role: "USER" as const,
  name: "Test Citizen",
};

const lawyerParty = {
  id: "LAWYER_0003",
  role: "LAWYER" as const,
  name: "Adv. Rohan Deshmukh",
};

describe("listConversations", () => {
  it("fetches the citizen's own inbox with the session token", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ count: 1, conversations: [SERVER_THREAD] }),
    );

    const threads = await listConversations(citizenParty);

    const [url, init] = lastCall();
    expect(String(url)).toMatch(/\/api\/chat\/conversations$/);
    expect(authHeader(init)).toBe("Bearer test-token");

    expect(threads).toHaveLength(1);
    const thread = threads[0];

    expect(thread.id).toBe("5");
    expect(thread.caseCnr).toBe("MHPU210000042026");
    expect(thread.updatedAt).toBe("2026-10-01 10:05:00");
    expect(thread.parties).toEqual([
      { id: "7", role: "USER", name: "Test Citizen" },
      {
        id: "LAWYER_0003",
        role: "LAWYER",
        name: "Adv. Rohan Deshmukh",
      },
    ]);
    expect(thread.messages[0]).toEqual({
      id: "11",
      senderId: "7",
      senderRole: "USER",
      body: "Namaste.",
      sentAt: "2026-10-01 10:00:00",
    });
    expect(thread.messages[1].senderRole).toBe("LAWYER");
  });

  it("sends an advocate to the lawyer-side inbox", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ count: 0, conversations: [] }),
    );

    const threads = await listConversations({
      id: "9",
      role: "LAWYER",
      name: "Adv. Rohan Deshmukh",
    });

    expect(String(lastCall()[0])).toMatch(
      /\/api\/chat\/lawyer\/conversations$/,
    );
    expect(threads).toEqual([]);
  });

  it("refuses ADMIN/STAFF locally instead of calling the API", async () => {
    await expect(
      listConversations({
        id: "1",
        role: "ADMIN",
        name: "Site Administrator",
      }),
    ).rejects.toThrow("Your account does not have a chat inbox.");

    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("startConversation", () => {
  it("sends only lawyer_id + case link for a citizen", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ ...SERVER_THREAD, messages: [] }),
    );

    const thread = await startConversation(
      citizenParty,
      lawyerParty,
      "MHPU210000042026",
    );

    const [url, init] = lastCall();
    expect(String(url)).toMatch(/\/api\/chat\/conversations$/);
    expect(init.method).toBe("POST");
    expect(lastBody()).toEqual({
      lawyer_id: "LAWYER_0003",
      case_cnr: "MHPU210000042026",
    });
    /* No identity fields — the server derives them from the token. */
    expect(lastBody()).not.toHaveProperty("user_id");
    expect(lastBody()).not.toHaveProperty("sender_id");

    expect(thread.id).toBe("5");
    expect(thread.messages).toEqual([]);
  });

  it("omits case_cnr entirely when none was given", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ ...SERVER_THREAD, messages: [] }),
    );

    await startConversation(citizenParty, lawyerParty);

    expect(lastBody()).toEqual({ lawyer_id: "LAWYER_0003" });
    expect(lastBody()).not.toHaveProperty("case_cnr");
  });

  it("sends only user_id for an advocate, with a real client id", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ ...SERVER_THREAD, messages: [] }),
    );

    await startConversation(
      { id: "9", role: "LAWYER", name: "Adv. Rohan Deshmukh" },
      { id: "42", role: "USER", name: "Asha Verma" },
      "MHPU210000042026",
    );

    const [url] = lastCall();
    expect(String(url)).toMatch(
      /\/api\/chat\/lawyer\/conversations$/,
    );
    expect(lastBody()).toEqual({
      user_id: 42,
      case_cnr: "MHPU210000042026",
    });
    expect(lastBody()).not.toHaveProperty("lawyer_id");
  });

  it("rejects a demo placeholder client id without calling the API", async () => {
    await expect(
      startConversation(
        { id: "9", role: "LAWYER", name: "Adv. Rohan Deshmukh" },
        { id: "USER_0001", role: "USER", name: "Asha Verma" },
      ),
    ).rejects.toThrow("That client account is not linked to NyayMitra yet.");

    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("sendMessage", () => {
  it("posts the trimmed body and maps the stored message back", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        id: 13,
        sender_id: 7,
        sender_role: "USER",
        message: "Padded but trimmed",
        created_at: "2026-10-01 11:00:00",
      }),
    );

    const message = await sendMessage(
      "5",
      citizenParty,
      "  Padded but trimmed  ",
    );

    const [url, init] = lastCall();
    expect(String(url)).toMatch(
      /\/api\/chat\/conversations\/5\/messages$/,
    );
    expect(init.method).toBe("POST");
    expect(lastBody()).toEqual({ message: "Padded but trimmed" });
    /* The sender is never in the payload. */
    expect(lastBody()).not.toHaveProperty("sender_id");

    expect(message).toEqual({
      id: "13",
      senderId: "7",
      senderRole: "USER",
      body: "Padded but trimmed",
      sentAt: "2026-10-01 11:00:00",
    });
  });

  it("refuses an empty message without calling the API", async () => {
    await expect(
      sendMessage("5", citizenParty, "   "),
    ).rejects.toThrow("Message cannot be empty.");

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("surfaces the backend's detail on a 403", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { detail: "Your lawyer registration is pending approval." },
        false,
        403,
      ),
    );

    await expect(
      sendMessage("5", citizenParty, "Hello"),
    ).rejects.toThrow("Your lawyer registration is pending approval.");
  });
});

describe("getConversation", () => {
  it("maps a found thread", async () => {
    fetchMock.mockResolvedValue(jsonResponse(SERVER_THREAD));

    const thread = await getConversation("5");

    expect(String(lastCall()[0])).toMatch(
      /\/api\/chat\/conversations\/5$/,
    );
    expect(thread?.id).toBe("5");
    expect(thread?.messages).toHaveLength(2);
  });

  it("returns null for an unknown thread (404 detail)", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { detail: "Conversation not found." },
        false,
        404,
      ),
    );

    await expect(getConversation("404")).resolves.toBeNull();
  });
});

describe("listAvailableLawyers", () => {
  it("maps the approved directory into picker parties", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        count: 1,
        lawyers: [
          {
            lawyer_id: "LAWYER_0009",
            full_name: "Adv. Meera Kulkarni",
            practice_areas: ["Family Law", "Cyber Law"],
            years_of_experience: 5,
            professional_bio: null,
            bar_council: null,
            verification_status: "APPROVED",
          },
        ],
      }),
    );

    const lawyers = await listAvailableLawyers();

    expect(String(lastCall()[0])).toMatch(/\/api\/chat\/lawyers$/);
    expect(lawyers).toHaveLength(1);
    expect(lawyers[0].id).toBe("LAWYER_0009");
    expect(lawyers[0].role).toBe("LAWYER");
    expect(lawyers[0].name).toBe("Adv. Meera Kulkarni");
    expect(lawyers[0].detail).toContain("Family Law, Cyber Law");
    expect(lawyers[0].detail).toContain("5 yrs experience");
  });

  it("lets the server's detail reach the caller on failure", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { detail: "Not authenticated. Please sign in to continue." },
        false,
        401,
      ),
    );

    await expect(listAvailableLawyers()).rejects.toThrow(
      "Not authenticated. Please sign in to continue.",
    );
  });
});

describe("deleteConversation", () => {
  it("refuses cleanly — the server keeps history by design", async () => {
    await expect(deleteConversation("5")).rejects.toThrow(
      "Deleting conversations is not available yet.",
    );

    expect(fetchMock).not.toHaveBeenCalled();
  });
});
