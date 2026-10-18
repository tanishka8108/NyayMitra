import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import CaseTimelinePage from "./CaseTimelinePage";
import { resetCases, saveCaseForUser } from "../../api/caseApi";
import { makeCase } from "../../test/caseFixtures";

/* =========================================================
   CASE TIMELINE — which cases the picker offers.

   The bug this file exists for: a citizen would save a CNR in
   My Cases and find the case there and nowhere else, because
   this page read the store through the ongoing filter while
   My Cases did not — so a saved record whose stage read
   "Case disposed" vanished from here. One store, four readers:
   the timeline reads every saved case, same as My Cases.

   Delay prediction's ongoing-only choice is asserted where it
   lives (caseApi.test.ts); this file is about this page's list.
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

describe("the timeline picker reads every saved case", () => {
  it("lists a saved case even after it has concluded", () => {
    saveCaseForUser(
      makeCase({
        cnr_number: "MHPU210000022026",
        current_case_stage: "Case disposed",
      }),
      ME,
    );

    render(<CaseTimelinePage userId={ME} onBack={() => {}} />);

    expect(screen.getByText("MHPU210000022026")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "View Timeline" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("No saved cases on this account"),
    ).not.toBeInTheDocument();
  });

  it("still lists an ongoing saved case", () => {
    saveCaseForUser(
      makeCase({
        cnr_number: "MHPU210000062026",
        current_case_stage: "Evidence",
      }),
      ME,
    );

    render(<CaseTimelinePage userId={ME} onBack={() => {}} />);

    expect(screen.getByText("MHPU210000062026")).toBeInTheDocument();
  });

  it("says so, honestly, when nothing has been saved", () => {
    render(<CaseTimelinePage userId={ME} onBack={() => {}} />);

    expect(
      screen.getByText("No saved cases on this account"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "View Timeline" }),
    ).not.toBeInTheDocument();
  });
});
