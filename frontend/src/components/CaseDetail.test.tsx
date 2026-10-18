import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CaseDetail from "./CaseDetail";
import { getGuidance } from "../api/guidanceApi";
import { makeCase } from "../test/caseFixtures";

/* =========================================================
   THE CASE DASHBOARD — what a record looks like once it is
   open: the order events arrive in, what is shown when the
   court has passed nothing, the door an order goes through,
   and the guidance panel's two answers.

   The API's own behaviour (ordering, status codes, the shape
   of the timeline) is covered on the service side; this is
   about the screen.
   ========================================================= */

vi.mock("../api/guidanceApi", () => ({
  getGuidance: vi.fn(),
}));

/*
 * The Court documents section (added to the matter) fetches
 * through caseDocumentApi — mocked so rendering a case here
 * never reaches for a backend that unit tests do not run.
 */
vi.mock("../api/caseDocumentApi", () => ({
  fetchCaseDocuments: vi.fn().mockResolvedValue({
    status: "empty",
    records: [],
    demo: false,
  }),
}));

const mockedGuidance = vi.mocked(getGuidance);

afterEach(() => {
  /* Vitest runs without globals here, so Testing Library cannot hook
     its own cleanup — unmount by hand, or the next test finds two of
     every element on the page. */
  cleanup();
  vi.clearAllMocks();
});

function renderDetail(
  overrides = {},
  props: { onOpenCourtOrders?: () => void } = {},
) {
  return render(
    <CaseDetail
      caseData={makeCase(overrides)}
      userId="USER_0001"
      onBack={vi.fn()}
      {...props}
    />,
  );
}

describe("case summary", () => {
  it("shows the CNR, the status the source recorded and where it came from", () => {
    renderDetail();

    expect(screen.getByRole("heading", { name: "MHPU210000042026" })).toBeInTheDocument();
    expect(screen.getByText("Case pending")).toBeInTheDocument();
    expect(screen.getByText(/not live eCourts data/i)).toBeInTheDocument();
  });

  it("marks a disposed matter as disposed", () => {
    renderDetail({ case_status: "Case disposed" });

    expect(screen.getByText("Case disposed")).toBeInTheDocument();
  });

  it("keeps a missing district visible as missing rather than inventing one", () => {
    renderDetail({ court_district: "Not available in the record." });

    expect(
      screen.getByText(/Not available in the record\., Maharashtra/),
    ).toBeInTheDocument();
  });
});

describe("timeline", () => {
  it("renders the journey oldest first, ending on the next hearing", () => {
    const { container } = renderDetail();

    const titles = Array.from(
      container.querySelectorAll(".matter-timeline li strong"),
    ).map((node) => node.textContent);

    expect(titles).toEqual([
      "Case filed",
      "Case registered",
      "Reply/Say",
      "Awaiting R and P",
      "Next hearing",
    ]);
  });

  it("falls back to the hearing list when the record has no journey", () => {
    const { container } = renderDetail({
      timeline: [],
      case_history_timeline: [
        {
          judge_title: "DISTRICT JUDGE - 1",
          business_on_date: "2026-01-07",
          hearing_date: "2026-01-07",
          purpose_of_hearing: "Reply/Say",
        },
      ],
    });

    expect(screen.getByRole("heading", { name: "Hearing history" })).toBeInTheDocument();

    const titles = Array.from(
      container.querySelectorAll(".matter-timeline li strong"),
    ).map((node) => node.textContent);

    expect(titles).toEqual(["Reply/Say"]);
  });

  it("says so when there is no timeline at all", () => {
    renderDetail({ timeline: [], case_history_timeline: [] });

    expect(
      screen.getByText(/no events are recorded for this case yet/i),
    ).toBeInTheDocument();
  });

  it("never offers a next hearing on a disposed case", () => {
    renderDetail({ case_status: "Case disposed", next_hearing_date: "" });

    expect(screen.queryByText("Next hearing")).not.toBeInTheDocument();
  });
});

describe("orders", () => {
  const order = {
    order_type: "INTERIM",
    order_number: "1",
    order_date: "2026-04-20",
    order_details: "Order on Exhibit",
    order_section: "Order",
  };

  it("lists the orders the court has passed", () => {
    renderDetail({ orders: [order] });

    expect(screen.getByText(/INTERIM Order No\. 1/)).toBeInTheDocument();
    expect(screen.getByText("Order on Exhibit")).toBeInTheDocument();
  });

  it("says there are none rather than showing a blank card", () => {
    renderDetail({ orders: [] });

    expect(
      screen.getByText(/no orders are recorded against this case yet/i),
    ).toBeInTheDocument();
  });

  it("offers the door to Court Orders when the shell has one", () => {
    const onOpenCourtOrders = vi.fn();

    renderDetail({ orders: [order] }, { onOpenCourtOrders });

    fireEvent.click(
      screen.getByRole("button", { name: /explain this order/i }),
    );

    expect(onOpenCourtOrders).toHaveBeenCalledTimes(1);
  });

  it("offers no button when there is no such door", () => {
    renderDetail({ orders: [order] });

    expect(
      screen.queryByRole("button", { name: /explain this order/i }),
    ).not.toBeInTheDocument();
  });

  it("shows no order card for a case this browser filed", () => {
    renderDetail({ data_source: undefined, orders: undefined });

    expect(screen.queryByText("Orders passed")).not.toBeInTheDocument();
  });
});

describe("next-steps guidance", () => {
  it("asks from this record's own status, stage and listing", async () => {
    mockedGuidance.mockResolvedValue({
      matched: true,
      stage: "Awaiting notice",
      urgency: "Routine",
      why: "",
      what_to_do_next: "Make sure the reply is served on the other side.",
      related_terms: [],
      candidates: [],
      disclaimer: "A lookup, not legal advice.",
    });

    renderDetail();

    fireEvent.click(
      screen.getByRole("button", { name: /what should i do next/i }),
    );

    expect(await screen.findByText(/reply is served/i)).toBeInTheDocument();
    expect(screen.getByText("Awaiting notice")).toBeInTheDocument();
    expect(screen.getByText("A lookup, not legal advice.")).toBeInTheDocument();

    const asked = mockedGuidance.mock.calls[0][0] as string;
    expect(asked).toContain("Case pending");
    expect(asked).toContain("Current stage: Awaiting Notice");
    expect(asked).toContain("Next hearing 12 Oct 2026");
  });

  it("says the service could not be reached when it fails", async () => {
    mockedGuidance.mockRejectedValue(new Error("connection refused"));

    renderDetail();

    fireEvent.click(
      screen.getByRole("button", { name: /what should i do next/i }),
    );

    expect(await screen.findByText(/guidance could not be reached/i)).toBeInTheDocument();
    expect(screen.queryByText(/reply is served/i)).not.toBeInTheDocument();
  });
});
