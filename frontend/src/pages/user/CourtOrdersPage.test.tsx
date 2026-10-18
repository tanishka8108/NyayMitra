import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import CourtOrdersPage from "./CourtOrdersPage";
import { resetCases, saveCaseForUser } from "../../api/caseApi";
import { makeCase } from "../../test/caseFixtures";

/* =========================================================
   COURT ORDERS — which cases the grouping offers.

   Same defect as the timeline: the grouping read the store
   through the ongoing filter, so the case whose FINAL orders a
   citizen most wants — the disposed one — was the one case the
   page refused to group. The page now reads every saved case,
   exactly as My Cases lists them.
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

describe("the orders grouping reads every saved case", () => {
  it("groups a saved case even after it has concluded", () => {
    saveCaseForUser(
      makeCase({
        cnr_number: "MHPU210000022026",
        current_case_stage: "Case disposed",
      }),
      ME,
    );

    render(<CourtOrdersPage userId={ME} onBack={() => {}} />);

    /* The CNR appears in the upload dropdown and in the group
       header — both come from the same list. */
    expect(
      screen.getAllByText(/MHPU210000022026/).length,
    ).toBeGreaterThan(0);
    expect(
      screen.queryByText("No saved cases on this account"),
    ).not.toBeInTheDocument();
  });

  it("says so, honestly, when nothing has been saved", () => {
    render(<CourtOrdersPage userId={ME} onBack={() => {}} />);

    expect(
      screen.getByText("No saved cases on this account"),
    ).toBeInTheDocument();
  });
});
