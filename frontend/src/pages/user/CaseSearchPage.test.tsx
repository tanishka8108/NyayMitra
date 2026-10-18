import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import CaseSearchPage from "./CaseSearchPage";
import { resetCases, saveCaseForUser } from "../../api/caseApi";
import { makeCase } from "../../test/caseFixtures";

/* =========================================================
   MY CASES — the page behind the dashboard.

   The flow this screen exists for: search an existing case by
   CNR, open it, save it, find it in the list. What is under
   test here is that the page offers exactly that flow and
   nothing else — in particular no way to "file a new case",
   and no copy claiming cases were filed on the account.

   The lookup service itself is not mocked away for the parts
   that matter: nothing in this test submits the form, because
   lookup behaviour is `CnrLookup.test.tsx`'s subject.
   ========================================================= */

const ME = "USER_TEST";

afterEach(() => {
  cleanup();
});

beforeEach(() => {
  /* Only the seeded fixture + whatever this test saves. */
  resetCases();
  window.localStorage.clear();
});

describe("the page never offers to file a case", () => {
  it("has no File a new case button or text anywhere on it", () => {
    render(<CaseSearchPage userId={ME} />);

    /* Scan the whole page, not a single element: the button was
       once offered in the header and again in the empty state. */
    expect(document.body.textContent).not.toMatch(
      /file a new case/i,
    );
    expect(
      screen.queryByRole("button", { name: /file a new case/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /file this case/i }),
    ).not.toBeInTheDocument();
  });

  it("offers the CNR search as the way a case gets in", () => {
    render(<CaseSearchPage userId={ME} />);

    expect(
      screen.getByText(/search by cnr number/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /look up case/i }),
    ).toBeInTheDocument();
  });

  it("describes the list as saved, not filed on the account", () => {
    render(<CaseSearchPage userId={ME} />);

    expect(
      screen.getByText(/only cases you have saved appear/i),
    ).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(
      /filed on your account/i,
    );
  });
});

describe("the empty state", () => {
  it("sends the reader to the CNR search instead of a filing form", () => {
    render(<CaseSearchPage userId={ME} />);

    expect(
      screen.getByText(/no saved cases yet/i),
    ).toBeInTheDocument();

    /* The empty state and the lookup's own copy both point at the
       same explicit step — at least one must be present. */
    expect(
      screen.getAllByText(/save to my cases/i).length,
    ).toBeGreaterThan(0);
  });
});

describe("a saved case appears under My Cases", () => {
  it("shows a case this account saved, by CNR and party", () => {
    saveCaseForUser(makeCase(), ME);

    render(<CaseSearchPage userId={ME} />);

    expect(
      screen.getByRole("heading", { name: "MHPU210000042026" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Vaibhav Bacche"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/1 saved case/i),
    ).toBeInTheDocument();
  });

  it("does not show another account's saved case", () => {
    saveCaseForUser(makeCase(), "SOMEONE_ELSE");

    render(<CaseSearchPage userId={ME} />);

    expect(
      screen.queryByRole("heading", { name: "MHPU210000042026" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/no saved cases yet/i),
    ).toBeInTheDocument();
  });
});
