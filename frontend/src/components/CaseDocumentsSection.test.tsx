import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CaseDocumentsSection from "./CaseDocumentsSection";
import {
  fetchCaseDocuments,
  type CaseDocumentsResult,
} from "../api/caseDocumentApi";

/* =========================================================
   COURT DOCUMENTS SECTION — the four states the screen can
   be in (loading, records, none, not-available) plus the two
   failure voices (no access, could-not-load), and the rule
   the whole feature exists for: a View/Download button is
   rendered only when the backend supplied a genuine URL, and
   demo rows are labelled, never passed off as real.

   The fetch itself (status mapping, URL sanitising) lives in
   caseDocumentApi and is exercised there; this is the screen.
   ========================================================= */

vi.mock("../api/caseDocumentApi", () => ({
  fetchCaseDocuments: vi.fn(),
}));

const mockedFetch = vi.mocked(fetchCaseDocuments);

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderSection(enabled = true) {
  return render(
    <CaseDocumentsSection cnr="MHPU210000042026" enabled={enabled} />,
  );
}

describe("court documents section", () => {
  it("renders nothing for a case with no service behind it", () => {
    const { container } = renderSection(false);

    expect(container).toBeEmptyDOMElement();
    expect(mockedFetch).not.toHaveBeenCalled();
  });

  it("shows a loading state while the fetch is in flight", () => {
    mockedFetch.mockReturnValue(
      new Promise<CaseDocumentsResult>(() => {}),
    );

    renderSection();

    expect(screen.getByRole("status")).toHaveTextContent(
      /fetching court documents/i,
    );
    expect(screen.getByRole("article")).toHaveAttribute(
      "aria-busy",
      "true",
    );
  });

  it("lists only the metadata the response carried, with live actions for real URLs", async () => {
    mockedFetch.mockResolvedValue({
      status: "ready",
      demo: false,
      records: [
        {
          id: "DOC_1",
          cnr: "MHPU210000042026",
          title: "Interim order on application",
          document_type: "Order",
          issued_at: "2026-04-20",
          file_name: "interim-order.pdf",
          size_bytes: 2048,
          view_url: "https://docs.nyaymitra.in/orders/DOC_1",
        },
      ],
    });

    renderSection();

    expect(
      await screen.findByText("Interim order on application"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Order · 20 Apr 2026 · interim-order.pdf · 2 KB/),
    ).toBeInTheDocument();

    const view = screen.getByRole("link", { name: "View" });
    expect(view).toHaveAttribute(
      "href",
      "https://docs.nyaymitra.in/orders/DOC_1",
    );

    /* No download_url was supplied → no download link is invented. */
    expect(
      screen.queryByRole("link", { name: "Download" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Download unavailable")).toBeInTheDocument();
  });

  it("offers no action at all when the backend sent no URLs", async () => {
    mockedFetch.mockResolvedValue({
      status: "ready",
      demo: false,
      records: [
        {
          id: "DOC_2",
          cnr: "MHPU210000042026",
          title: "Notice of hearing",
        },
      ],
    });

    renderSection();

    expect(await screen.findByText("Notice of hearing")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText("View unavailable")).toBeInTheDocument();
  });

  it("labels demo rows so sample data never reads as a record", async () => {
    mockedFetch.mockResolvedValue({
      status: "ready",
      demo: true,
      records: [
        {
          id: "demo-1",
          cnr: "MHPU210000042026",
          title: "Sample interim order (demo record)",
        },
      ],
    });

    renderSection();

    expect(
      await screen.findByText(/development demo data/i),
    ).toBeInTheDocument();
    expect(screen.getByText("DEMO")).toBeInTheDocument();
  });

  it("says none are published yet when the list comes back empty", async () => {
    mockedFetch.mockResolvedValue({
      status: "empty",
      records: [],
      demo: false,
    });

    renderSection();

    expect(
      await screen.findByText(
        /no court documents have been published for this case yet/i,
      ),
    ).toBeInTheDocument();
  });

  it("separates “not available yet” from “no documents”", async () => {
    mockedFetch.mockResolvedValue({
      status: "unavailable",
      records: [],
      demo: false,
    });

    renderSection();

    expect(
      await screen.findByText(
        /court documents are not available for this case yet/i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/no court documents have been published/i),
    ).not.toBeInTheDocument();
  });

  it("tells a signed-out reader to sign in again", async () => {
    mockedFetch.mockResolvedValue({
      status: "signed-out",
      records: [],
      demo: false,
    });

    renderSection();

    expect(
      await screen.findByText(/sign in again/i),
    ).toBeInTheDocument();
  });

  it("says access is denied without implying a failure", async () => {
    mockedFetch.mockResolvedValue({
      status: "forbidden",
      records: [],
      demo: false,
    });

    renderSection();

    expect(
      await screen.findByText(/do not have access/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("alert"),
    ).not.toBeInTheDocument();
  });

  it("reports a failure as a plain message with a retry that refetches", async () => {
    mockedFetch.mockResolvedValue({
      status: "error",
      records: [],
      demo: false,
    });

    renderSection();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/could not be loaded/i);
    expect(mockedFetch).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: /try again/i }));

    await waitFor(() =>
      expect(mockedFetch).toHaveBeenCalledTimes(2),
    );
  });
});
