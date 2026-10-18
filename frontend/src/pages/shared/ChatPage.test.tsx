import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ChatPage from "./ChatPage";

import { saveSession } from "../../auth/session";
import type { Session } from "../../auth/session";

/* =========================================================
   CHAT PAGE — the shared inbox in API mode (Phase 3).

   A stubbed `fetch` stands in for the real /api/chat endpoints.
   What is under test here is the screen the brief asks for:

   - the empty, loading and error states read correctly (a 401
     surfaces the server's sentence, not a fake empty inbox);
   - "New chat" lists the verified lawyer directory the server
     returns, with the profile line under each name;
   - choosing a lawyer POSTs a conversation and opens the thread;
   - an existing thread renders its full history;
   - the composer sends a message;
   - no delete control exists server-side, so none is shown.

   The wire contract itself is chatApi.test.ts; the authorization
   rules are NyayMitra-feature-lawyer-api/tests/test_chat_api.py.
   ========================================================= */

const SESSION: Session = {
  userId: "7",
  fullName: "Test Citizen",
  email: "citizen@example.com",
  role: "USER",
  token: "test-token",
  loginAt: "2026-10-01T00:00:00.000Z",
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

const DIRECTORY = {
  count: 2,
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
    {
      lawyer_id: "LAWYER_0011",
      full_name: "Adv. Imran Sheikh",
      practice_areas: ["Criminal Law"],
      years_of_experience: 12,
      professional_bio: null,
      bar_council: null,
      verification_status: "APPROVED",
    },
  ],
};

const THREAD = {
  id: 5,
  user_id: 7,
  user_name: "Test Citizen",
  lawyer_id: "LAWYER_0003",
  lawyer_name: "Adv. Rohan Deshmukh",
  case_cnr: null,
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

let nextMessageId = 100;

/** Route the stubbed fetch the way the backend routes requests. */
function stubApi(initialThreads: unknown[] = []) {
  const state = {
    threads: JSON.parse(JSON.stringify(initialThreads)) as Record<
      string,
      never
    >[],
  };

  fetchMock.mockImplementation(
    (url: unknown, init?: RequestInit) => {
      const target = String(url);
      const method = init?.method ?? "GET";

      if (target.includes("/messages") && method === "POST") {
        const body = JSON.parse(String(init?.body)) as {
          message: string;
        };

        const stored = {
          id: nextMessageId++,
          sender_id: 7,
          sender_role: "USER",
          message: body.message,
          created_at: "2026-10-01 12:00:00",
        };

        const thread = state.threads[0] as unknown as
          | { messages: Record<string, unknown>[] }
          | undefined;
        thread?.messages.push(stored);

        return Promise.resolve(jsonResponse(stored, true, 201));
      }

      if (target.includes("/api/chat/lawyers")) {
        return Promise.resolve(jsonResponse(DIRECTORY));
      }

      if (target.includes("/api/chat/conversations")) {
        if (method === "POST") {
          const body = JSON.parse(String(init?.body)) as {
            lawyer_id: string;
          };
          const lawyer = DIRECTORY.lawyers.find(
            (entry) => entry.lawyer_id === body.lawyer_id,
          );

          const created = {
            id: 9,
            user_id: 7,
            user_name: "Test Citizen",
            lawyer_id: body.lawyer_id,
            lawyer_name: lawyer?.full_name ?? "Advocate",
            case_cnr: null,
            created_at: "2026-10-01 12:00:00",
            updated_at: "2026-10-01 12:00:00",
            messages: [],
          };

          state.threads.push(
            created as unknown as (typeof state.threads)[number],
          );

          return Promise.resolve(jsonResponse(created, true, 201));
        }

        return Promise.resolve(
          jsonResponse({
            count: state.threads.length,
            conversations: state.threads,
          }),
        );
      }

      return Promise.resolve(
        jsonResponse({ detail: "Conversation not found." }, false, 404),
      );
    },
  );

  return state;
}

function postBodies(): Record<string, unknown>[] {
  return fetchMock.mock.calls
    .filter(([, init]) => (init as RequestInit | undefined)?.method === "POST")
    .map(([, init]) =>
      JSON.parse(String((init as RequestInit).body)),
    ) as Record<string, unknown>[];
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  saveSession(SESSION);

  /* jsdom implements no scrolling — the auto-scroll effect needs
     this once a thread is open. Browsers have it natively. */
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  window.localStorage.clear();
});

describe("the empty state", () => {
  it("says there are no conversations yet", async () => {
    stubApi();

    render(<ChatPage session={SESSION} />);

    expect(
      await screen.findByText("No conversations yet."),
    ).toBeInTheDocument();
  });
});

describe("the error state", () => {
  it("surfaces the server's sentence instead of an empty inbox", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { detail: "Your session has expired. Please sign in again." },
        false,
        401,
      ),
    );

    render(<ChatPage session={SESSION} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Your session has expired. Please sign in again.",
    );
  });
});

describe("the verified lawyer listing", () => {
  it("offers the approved directory under New chat", async () => {
    stubApi();

    render(<ChatPage session={SESSION} />);
    await screen.findByText("No conversations yet.");

    fireEvent.click(
      screen.getByRole("button", { name: /new chat/i }),
    );

    expect(
      await screen.findByText("Adv. Meera Kulkarni"),
    ).toBeInTheDocument();
    expect(screen.getByText("Adv. Imran Sheikh")).toBeInTheDocument();

    /* The profile line the picker shows under each name. */
    expect(
      screen.getByText(/Lawyer · Family Law, Cyber Law/),
    ).toBeInTheDocument();
  });

  it("opens a conversation when a lawyer is chosen", async () => {
    stubApi();

    render(<ChatPage session={SESSION} />);
    await screen.findByText("No conversations yet.");

    fireEvent.click(
      screen.getByRole("button", { name: /new chat/i }),
    );
    fireEvent.click(
      await screen.findByRole("button", {
        name: /Adv. Meera Kulkarni/,
      }),
    );

    /* The blank thread opens: composer addressed to the advocate. */
    expect(
      await screen.findByText(/no messages yet — say hello/i),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText("Message"),
    ).toHaveAttribute(
      "placeholder",
      "Message Adv. Meera Kulkarni…",
    );

    /* And the request carried only the target lawyer's id. */
    await waitFor(() => {
      expect(postBodies()).toContainEqual({
        lawyer_id: "LAWYER_0009",
      });
    });
  });
});

describe("an existing thread", () => {
  it("renders the history without a delete control", async () => {
    stubApi([THREAD]);

    render(<ChatPage session={SESSION} />);

    expect(await screen.findByText("Namaste.")).toBeInTheDocument();
    /* The sidebar preview and the bubble both quote the last
       message — either one proves the history rendered. */
    expect(
      screen.getAllByText("How can I help?").length,
    ).toBeGreaterThan(0);

    /* The server keeps history by design — no ✕ is offered. */
    expect(
      document.querySelector(".chat-thread-delete"),
    ).toBeNull();
  });

  it("sends the draft and shows the stored message", async () => {
    stubApi([THREAD]);

    render(<ChatPage session={SESSION} />);
    await screen.findByText("Namaste.");

    fireEvent.change(screen.getByLabelText("Message"), {
      target: { value: "Please review my case." },
    });
    /* Submit the form directly, as RegisterPage.test does — jsdom's
       native form validation on button clicks is browser territory. */
    fireEvent.submit(
      document.querySelector(".chat-composer") as HTMLFormElement,
    );

    expect(
      await screen.findByText("Please review my case."),
    ).toBeInTheDocument();

    expect(postBodies()).toContainEqual({
      message: "Please review my case.",
    });
  });
});
