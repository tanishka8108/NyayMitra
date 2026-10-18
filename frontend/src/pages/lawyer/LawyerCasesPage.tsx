import { useMemo } from "react";
import { Scale, MessageSquare } from "lucide-react";

import { getCasesForLawyer } from "../../api/caseApi";
import { listDocuments } from "../../api/documentApi";
import type { Case } from "../../types/case";
import type { ChatTarget } from "../../api/chatApi";

import "./LawyerCasesPage.css";

/* =========================================================
   LAWYER — ACTIVE CASES

   The advocate's own caseload: only matters where
   handling_lawyer_id matches the signed-in lawyer, so one
   advocate never sees another's files.

   Each card carries the full detail the brief asked for —
   parties, stage, judge, next hearing, metrics, the recent
   history, and both the documents on file and the orders the
   court has passed — rather than just a title and a link.

   "Message client" jumps straight into the chat thread with
   the person who owns the case, which is where the ongoing
   conversation about it lives.
   ========================================================= */

type LawyerCasesPageProps = {
  lawyerId: string;
  onBack?: () => void;
  onOpenChat: (target: ChatTarget) => void;
};

function formatHearingDate(iso: string): string {
  const parsed = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return iso;

  return parsed.toLocaleDateString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function daysUntil(iso: string): number | null {
  const parsed = new Date(`${iso}T00:00:00`).getTime();
  if (Number.isNaN(parsed)) return null;

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  return Math.round((parsed - today.getTime()) / 86_400_000);
}

function LawyerCasesPage({
  lawyerId,
  onBack,
  onOpenChat,
}: LawyerCasesPageProps) {
  /* Read on every render rather than memoised on lawyerId:
     a citizen can file a new matter and name this advocate as
     its handler while the tab is open, and the caseload
     should pick that up without a reload. */
  const myCases = getCasesForLawyer(lawyerId);

  /* The nearest upcoming hearing across the whole caseload. */
  const nextHearing = useMemo(() => {
    const dated = myCases
      .map((item) => item.next_hearing_date)
      .filter(Boolean)
      .sort();

    return dated[0] ?? null;
  }, [myCases]);

  const totalAge = myCases.reduce(
    (sum, item) => sum + (item.calculated_metrics?.total_case_age_days ?? 0),
    0,
  );

  /* Human label for the next hearing. Written out here rather than inline so
     an already-passed date reads as a scheduling state, not an error. */
  const nextHearingLabel = (() => {
    if (!nextHearing) return "Not scheduled";

    const days = daysUntil(nextHearing);
    if (days === null) return "Not scheduled";
    if (days < 0) return "Awaiting reschedule";
    if (days === 0) return "Today";

    return `In ${days} day${days === 1 ? "" : "s"}`;
  })();

  if (myCases.length === 0) {
    return (
      <main className="nyaymitra-page lawyer-cases-page">
        {onBack && (
          <div className="page-back-wrapper">
            <button className="page-back-button" onClick={onBack}>
              ← Back to Dashboard
            </button>
          </div>
        )}

        <section className="lawyer-cases-hero">
          <div className="eyebrow">
            <Scale size={15} aria-hidden="true" />
            NYAYMITRA ADVOCATE PORTAL
          </div>

          <h1>
            Active
            <br />
            <span>matters</span>
          </h1>

          <p>No matters are currently assigned to you.</p>
        </section>

        <div className="lawyer-cases-empty">
          <span aria-hidden="true"><Scale size={22} /></span>
          <p>
            Once a case is assigned to you it will appear here with
            its stage, hearing schedule and parties.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="nyaymitra-page lawyer-cases-page">
      {onBack && (
        <div className="page-back-wrapper">
          <button className="page-back-button" onClick={onBack}>
            ← Back to Dashboard
          </button>
        </div>
      )}

      <section className="lawyer-cases-hero">
        <div className="eyebrow">
          <Scale size={15} aria-hidden="true" />
          NYAYMITRA ADVOCATE PORTAL
        </div>

        <h1>
          Active
          <br />
          <span>matters</span>
        </h1>

        <p>
          Every case assigned to you, with the parties, current stage
          and hearing schedule. Only your own caseload is listed.
        </p>
      </section>

      {/* ---------- summary ---------- */}

      <div className="lawyer-cases-stats">
        <div className="lawyer-cases-stat">
          <span>ACTIVE MATTERS</span>
          <strong>{myCases.length}</strong>
          <small>Assigned to you</small>
        </div>

        <div className="lawyer-cases-stat">
          <span>NEXT HEARING</span>
          <strong>
            {nextHearing ? formatHearingDate(nextHearing) : "—"}
          </strong>
          <small>{nextHearingLabel}</small>
        </div>

        <div className="lawyer-cases-stat">
          <span>TOTAL CASE AGE</span>
          <strong>{totalAge}</strong>
          <small>Days across all matters</small>
        </div>

        <div className="lawyer-cases-stat">
          <span>HEARINGS BOOKED</span>
          <strong>
            {myCases.reduce(
              (sum, item) =>
                sum + (item.calculated_metrics?.total_hearings_scheduled ?? 0),
              0,
            )}
          </strong>
          <small>Scheduled to date</small>
        </div>
      </div>

      {/* ---------- case list ---------- */}

      <div className="lawyer-cases-list">
        {myCases.map((item) => (
          <CaseDetailCard
            key={item.cnr_number}
            caseData={item}
            onMessageClient={(target) => onOpenChat(target)}
          />
        ))}
      </div>
    </main>
  );
}

/* =========================================================
   ONE MATTER
   ========================================================= */

function CaseDetailCard({
  caseData,
  onMessageClient,
}: {
  caseData: Case;
  onMessageClient: (target: ChatTarget) => void;
}) {
  const countdown = daysUntil(caseData.next_hearing_date);

  /* Read on every render, for the same reason the page does: the
     client can upload a paper while this tab is open and the
     matter should show it without a reload. Court orders are
     pulled out separately because they answer a different
     question — what the court has decided, not what is on file. */
  const files = listDocuments(caseData.cnr_number);
  const orders = files.filter((doc) => doc.category === "Court order");
  const papers = files.filter((doc) => doc.category !== "Court order");

  return (
    <article className="case-detail">
      <header className="case-detail-head">
        <div>
          <span className="case-detail-type">{caseData.case_type}</span>
          <h2>{caseData.cnr_number}</h2>
          <p className="case-detail-court">{caseData.court_name}</p>
        </div>

        <div className="case-detail-stage">
          <span>CURRENT STAGE</span>
          <strong>{caseData.current_case_stage}</strong>
          <small>
            {caseData.calculated_metrics.current_stage_duration_days} days
            at this stage
          </small>
        </div>

        <div className="case-detail-stage case-detail-next">
          <span>NEXT HEARING</span>
          <strong>
            {caseData.next_hearing_date
              ? formatHearingDate(caseData.next_hearing_date)
              : "Not listed"}
          </strong>
          <small>
            {countdown === null
              ? "Awaiting a date"
              : countdown < 0
                ? "Passed — needs rescheduling"
                : countdown === 0
                  ? "Today"
                  : `In ${countdown} day${countdown === 1 ? "" : "s"}`}
          </small>
        </div>
      </header>

      <div className="case-detail-grid">
        {/* parties */}
        <div className="case-detail-block">
          <h3>Parties</h3>
          <dl>
            <div>
              <dt>Client (petitioner)</dt>
              <dd>{caseData.petitioner_name}</dd>
            </div>
            <div>
              <dt>Opposing advocate</dt>
              <dd>{caseData.petitioner_advocate || "—"}</dd>
            </div>
            <div>
              <dt>Respondents ({caseData.respondents_list.length})</dt>
              <dd>{caseData.respondents_list.join(", ")}</dd>
            </div>
          </dl>
        </div>

        {/* court */}
        <div className="case-detail-block">
          <h3>Court</h3>
          <dl>
            <div>
              <dt>Presiding judge</dt>
              <dd>{caseData.presiding_judge}</dd>
            </div>
            <div>
              <dt>District</dt>
              <dd>
                {caseData.court_district}, {caseData.court_state}
              </dd>
            </div>
            <div>
              <dt>Provision</dt>
              <dd>
                {caseData.applied_act}
                {caseData.applied_section
                  ? ` · S. ${caseData.applied_section}`
                  : ""}
              </dd>
            </div>
          </dl>
        </div>

        {/* schedule */}
        <div className="case-detail-block">
          <h3>Schedule</h3>
          <dl>
            <div>
              <dt>Filed</dt>
              <dd>{formatHearingDate(caseData.filing_date)}</dd>
            </div>
            <div>
              <dt>First hearing</dt>
              <dd>{formatHearingDate(caseData.first_hearing_date)}</dd>
            </div>
            <div>
              <dt>Next hearing</dt>
              <dd>
                {formatHearingDate(caseData.next_hearing_date)}
                {countdown === 0
                  ? " · today"
                  : countdown !== null && countdown > 0
                    ? ` · in ${countdown} day${
                        countdown === 1 ? "" : "s"
                      }`
                    : ""}
              </dd>
            </div>
          </dl>
        </div>

        {/* metrics */}
        <div className="case-detail-block">
          <h3>At a glance</h3>
          <ul className="case-detail-metrics">
            <li>
              <strong>{caseData.calculated_metrics.total_case_age_days}</strong>
              <span>days old</span>
            </li>
            <li>
              <strong>
                {caseData.calculated_metrics.total_hearings_scheduled}
              </strong>
              <span>hearings</span>
            </li>
            <li>
              <strong>{caseData.calculated_metrics.respondent_count}</strong>
              <span>respondents</span>
            </li>
          </ul>
        </div>
      </div>

      {/* history */}
      <div className="case-detail-history">
        <h3>Recent history</h3>

        <ol>
          {caseData.case_history_timeline.map((entry, index) => (
            <li key={`${entry.hearing_date}-${index}`}>
              <time>{formatHearingDate(entry.hearing_date)}</time>
              <div>
                <strong>{entry.purpose_of_hearing}</strong>
                <span>{entry.judge_title}</span>
              </div>
            </li>
          ))}
        </ol>
      </div>

      {/* documents + orders */}
      <div className="case-detail-files">

        <section>
          <h3>
            Documents on file
            <span>{papers.length}</span>
          </h3>

          {papers.length > 0 ? (
            <ul className="case-detail-file-list">
              {papers.map((doc) => (
                <li key={doc.id}>
                  <span className="case-detail-file-cat">
                    {doc.category}
                  </span>

                  <strong>{doc.name}</strong>

                  <time>{formatHearingDate(doc.uploadedAt.slice(0, 10))}</time>
                </li>
              ))}
            </ul>
          ) : (
            <p className="case-detail-files-empty">
              Nothing has been uploaded against this matter yet.
            </p>
          )}
        </section>

        <section>
          <h3>
            Court orders
            <span>{orders.length}</span>
          </h3>

          {orders.length > 0 ? (
            <ul className="case-detail-file-list">
              {orders.map((doc) => (
                <li key={doc.id}>
                  <span className="case-detail-file-cat is-order">
                    Order
                  </span>

                  <strong>{doc.name}</strong>

                  <time>{formatHearingDate(doc.uploadedAt.slice(0, 10))}</time>
                </li>
              ))}
            </ul>
          ) : (
            <p className="case-detail-files-empty">
              No order has been recorded for this matter.
            </p>
          )}
        </section>

      </div>

      <footer className="case-detail-foot">
        <span className="case-detail-client">
          Client: {caseData.petitioner_name}
        </span>

        <button
          type="button"
          className="case-detail-chat"
          onClick={() =>
            onMessageClient({
              id: caseData.owner_user_id,
              name: caseData.petitioner_name,
              role: "USER",
              caseCnr: caseData.cnr_number,
            })
          }
        >
          <MessageSquare size={14} aria-hidden="true" />
          Message client
        </button>
      </footer>
    </article>
  );
}

export default LawyerCasesPage;
