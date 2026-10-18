import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CnrLookup from "./CnrLookup";
import {
  isSavedForUser,
  lookupCaseByCnr,
  saveCaseForUser,
} from "../api/caseApi";
import { makeCase } from "../test/caseFixtures";

/* =========================================================
   CNR LOOKUP — the states the screen can be in.

   The service is mocked, so what is under test is this
   component's own behaviour: what it says before anything is
   typed, what it refuses to send, what it shows while waiting,
   what it shows when the answer is a refusal or no answer at
   all, and that saving to My Cases happens only through the
   explicit save button. The service's real responses are
   covered by `NyayMitra-feature-lawyer-api/tests`.
   ========================================================= */

vi.mock("../api/caseApi", () => ({
  lookupCaseByCnr: vi.fn(),
  isSavedForUser: vi.fn(),
  saveCaseForUser: vi.fn(),
}));

const mockedLookup = vi.mocked(lookupCaseByCnr);
const mockedIsSaved = vi.mocked(isSavedForUser);
const mockedSave = vi.mocked(saveCaseForUser);

const CNR = "MHPU210000042026";

beforeEach(() => {
  /* Deterministic defaults for the store functions: nothing is
     saved yet, and saving tags the record with the account.
     Tests that are about the saved state override these. */
  mockedIsSaved.mockReturnValue(false);
  mockedSave.mockImplementation((record, userId) => ({
    ...record,
    owner_user_id: userId,
  }));
});

afterEach(() => {
  /* Vitest runs without globals here, so Testing Library cannot hook
     its own cleanup — unmount by hand, or the next test finds two
     of every element on the page. */
  cleanup();
  vi.clearAllMocks();
});

function typeCnr(value: string): void {
  fireEvent.change(screen.getByLabelText("CNR number"), {
    target: { value },
  });
}

function submit(): void {
  fireEvent.submit(screen.getByRole("button", { name: /look up case/i }));
}

describe("empty state", () => {
  it("says what to type and will not send anything yet", () => {
    render(<CnrLookup userId="USER_0001" onOpen={vi.fn()} />);

    expect(
      screen.getByText(/enter a cnr to search/i),
    ).toBeInTheDocument();

    expect(
      screen.getByRole("button", { name: /look up case/i }),
    ).toBeDisabled();

    expect(mockedLookup).not.toHaveBeenCalled();
  });

  it("refuses an empty submit with a message instead of a request", () => {
    render(<CnrLookup userId="USER_0001" onOpen={vi.fn()} />);

    fireEvent.submit(
      document.querySelector(".cnr-lookup-form") as HTMLFormElement,
    );

    expect(
      screen.getByRole("alert"),
    ).toHaveTextContent(/enter the cnr of the case you want to open/i);
    expect(mockedLookup).not.toHaveBeenCalled();
  });
});

describe("character validation", () => {
  it("counts what is missing while the number is being typed", () => {
    render(<CnrLookup userId="USER_0001" onOpen={vi.fn()} />);

    typeCnr("MHPU21");   // 6 characters of a 16 character number

    expect(screen.getByText(/10 more to go/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /look up case/i }),
    ).toBeDisabled();
  });

  it("explains a complete but malformed number", () => {
    render(<CnrLookup userId="USER_0001" onOpen={vi.fn()} />);

    typeCnr("1234567890123456");

    expect(
      screen.getByText(/four letters then twelve digits/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /look up case/i }),
    ).toBeDisabled();
  });

  it("normalises case and separators before sending", async () => {
    mockedLookup.mockResolvedValue(makeCase());

    render(<CnrLookup userId="USER_0001" onOpen={vi.fn()} />);

    typeCnr("  mhpu-2100 0004_2026 ");
    submit();

    await waitFor(() =>
      expect(mockedLookup).toHaveBeenCalledWith(CNR, "USER_0001"),
    );
  });
});

describe("loading state", () => {
  it("says it is looking up and disables the button while waiting", async () => {
    mockedLookup.mockReturnValue(new Promise(() => {}));

    render(<CnrLookup userId="USER_0001" onOpen={vi.fn()} />);

    typeCnr(CNR);
    submit();

    const busy = await screen.findByRole("button", {
      name: /looking up/i,
    });

    expect(busy).toBeDisabled();
    expect(mockedLookup).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("error state", () => {
  it("shows the service's own refusal", async () => {
    mockedLookup.mockRejectedValue(
      new Error("MHPU999999992026 is not in the development dataset."),
    );

    render(<CnrLookup userId="USER_0001" onOpen={vi.fn()} />);

    typeCnr(CNR);
    submit();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /is not in the development dataset/i,
    );

    // A refusal clears the button back rather than leaving it stuck.
    expect(
      screen.getByRole("button", { name: /look up case/i }),
    ).toBeEnabled();
  });

  it("distinguishes an unreachable service from a rejected number", async () => {
    mockedLookup.mockRejectedValue(
      new TypeError("Failed to fetch"),
    );

    render(<CnrLookup userId="USER_0001" onOpen={vi.fn()} />);

    typeCnr(CNR);
    submit();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /could not be reached/i,
    );
  });

  it("shows the message again as soon as the number is edited", async () => {
    mockedLookup.mockRejectedValue(new Error("Not found."));

    render(<CnrLookup userId="USER_0001" onOpen={vi.fn()} />);

    typeCnr(CNR);
    submit();

    await screen.findByRole("alert");

    typeCnr(CNR + "0");

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("successful lookup", () => {
  it("opens the record on the page the caller hands over", async () => {
    const found = makeCase();
    const onOpen = vi.fn();

    mockedLookup.mockResolvedValue(found);

    render(<CnrLookup userId="USER_0001" onOpen={onOpen} />);

    typeCnr(CNR);
    submit();

    const open = await screen.findByRole("button", {
      name: /open full case/i,
    });

    fireEvent.click(open);

    expect(onOpen).toHaveBeenCalledWith(found);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("says plainly that the record is development data", async () => {
    mockedLookup.mockResolvedValue(makeCase());

    render(<CnrLookup userId="USER_0001" onOpen={vi.fn()} />);

    typeCnr(CNR);
    submit();

    expect(await screen.findByText(/not live eCourts data/i)).toBeInTheDocument();
  });
});

describe("saving to My Cases", () => {
  it("offers saving beside opening, and a lookup alone never saves", async () => {
    mockedLookup.mockResolvedValue(makeCase());

    render(<CnrLookup userId="USER_0001" onOpen={vi.fn()} />);

    typeCnr(CNR);
    submit();

    await screen.findByRole("button", { name: /open full case/i });

    /* The lookup is a read. Nothing enters My Cases until the
       save button is pressed. */
    expect(mockedSave).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: /^save to my cases$/i }),
    ).toBeEnabled();
  });

  it("saves the looked-up record for this account and marks it saved", async () => {
    const found = makeCase();

    mockedLookup.mockResolvedValue(found);

    render(<CnrLookup userId="USER_0001" onOpen={vi.fn()} />);

    typeCnr(CNR);
    submit();

    const save = await screen.findByRole("button", {
      name: /^save to my cases$/i,
    });

    fireEvent.click(save);

    expect(mockedSave).toHaveBeenCalledWith(found, "USER_0001");

    /* The button becomes the saved state and stops offering the
       action — the record the user saw is the one that is kept. */
    expect(
      screen.getByRole("button", { name: /saved to my cases/i }),
    ).toBeDisabled();
  });

  it("reads as already saved when the account already has the case", async () => {
    mockedLookup.mockResolvedValue(makeCase());
    mockedIsSaved.mockReturnValue(true);

    render(<CnrLookup userId="USER_0001" onOpen={vi.fn()} />);

    typeCnr(CNR);
    submit();

    const saved = await screen.findByRole("button", {
      name: /saved to my cases/i,
    });

    expect(saved).toBeDisabled();
    expect(mockedSave).not.toHaveBeenCalled();
  });

  it("opening the full case never saves behind the reader's back", async () => {
    const onOpen = vi.fn();

    mockedLookup.mockResolvedValue(makeCase());

    render(<CnrLookup userId="USER_0001" onOpen={onOpen} />);

    typeCnr(CNR);
    submit();

    fireEvent.click(
      await screen.findByRole("button", { name: /open full case/i }),
    );

    expect(onOpen).toHaveBeenCalled();
    expect(mockedSave).not.toHaveBeenCalled();
  });
});
