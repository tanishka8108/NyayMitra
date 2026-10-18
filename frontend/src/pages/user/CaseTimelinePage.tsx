import { useState } from "react";
import {
  Scale,
  FileText,
  MessageSquare,
  Calendar,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

import OngoingCases from "../../components/OngoingCases";
import { getCasesForUser } from "../../api/caseApi";
import type { Case } from "../../types/case";

/* =========================================================
   CASE TIMELINE

   No CNR field. The screen lists the account's saved matters
   with a "View Timeline" on each, and then draws that case's
   own history — the filing, every proceeding recorded against
   it, the stage it sits at today, and what is listed next.

   The old version rendered a fixed six-step sample regardless
   of what was typed, so every case told the same story. The
   events below are built from the record instead: two matters
   side by side now produce visibly different timelines, which
   is the entire point of the screen.
   ========================================================= */

type CaseTimelinePageProps = {
  userId: string;
  onBack: () => void;
};

type TimelineEvent = {
  date: string;
  title: string;
  description: string;
  status: "completed" | "current" | "upcoming";
  icon: LucideIcon;
};

function formatDate(iso: string): string {
  if (!iso) return "Not recorded";

  const parsed = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return iso;

  return parsed.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function isFuture(iso: string): boolean {
  const parsed = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return false;

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  return parsed >= today;
}

/**
 * Build the journey from the case record.
 *
 * Past hearings come first, then where the matter stands now,
 * then what is listed — which is the order a reader thinks in,
 * and it falls out of the dates rather than being asserted.
 */
function buildTimeline(caseData: Case): TimelineEvent[] {
  const entries = caseData.case_history_timeline ?? [];

  const past: TimelineEvent[] = [];
  const upcoming: TimelineEvent[] = [];

  for (const entry of entries) {
    /* A newly filed case carries one entry saying as much; the
       "Case filed" event above already covers it, so showing it
       twice would just be the same fact in two places. */
    if (
      entry.purpose_of_hearing === "Case filed and registered" &&
      entry.hearing_date === caseData.filing_date
    ) {
      continue;
    }

    const event: TimelineEvent = {
      date: formatDate(entry.hearing_date),
      title: entry.purpose_of_hearing || "Hearing held",
      description:
        entry.judge_title && entry.judge_title !== "Pending"
          ? `Before ${entry.judge_title}.`
          : "Recorded in the case history.",
      status: isFuture(entry.hearing_date) ? "upcoming" : "completed",
      icon: Scale,
    };

    if (event.status === "upcoming") upcoming.push(event);
    else past.push(event);
  }

  const events: TimelineEvent[] = [
    {
      date: formatDate(caseData.filing_date),
      title: "Case filed",
      description: `Registered before ${caseData.court_name}.`,
      status: "completed",
      icon: FileText,
    },
    ...past,
    {
      date: "Now",
      title: caseData.current_case_stage,
      description: "The stage this matter sits at today.",
      status: "current",
      icon: MessageSquare,
    },
    ...upcoming,
  ];

  /* Nothing listed ahead of today — say so plainly instead of
     leaving the reader to wonder whether the list is complete. */
  if (upcoming.length === 0) {
    const hasDate = Boolean(caseData.next_hearing_date);

    events.push({
      date: hasDate ? formatDate(caseData.next_hearing_date) : "To be decided",
      title: "Next hearing",
      description: hasDate
        ? `The matter is next listed before ${
            caseData.presiding_judge || "the court"
          }.`
        : "No date is on record yet — the court will list the matter in its own time.",
      status: "upcoming",
      icon: Calendar,
    });
  }

  events.push({
    date: "To be decided",
    title: "Decision",
    description:
      "The final decision will be recorded after the remaining proceedings.",
    status: "upcoming",
    icon: Scale,
  });

  return events;
}

export default function CaseTimelinePage({
  userId,
  onBack,
}: CaseTimelinePageProps) {
  const cases = getCasesForUser(userId);

  const [selected, setSelected] = useState<Case | null>(null);
  const [busyCnr, setBusyCnr] = useState<string | null>(null);

  const show = (caseData: Case) => {
    if (busyCnr) return;

    setBusyCnr(caseData.cnr_number);

    window.setTimeout(() => {
      setSelected(caseData);
      setBusyCnr(null);
    }, 300);
  };

  const events = selected ? buildTimeline(selected) : null;

  return (
    <main className="case-timeline-page">
      {/* =====================================================
          BACK
          ===================================================== */}

      <button type="button" className="case-timeline-back" onClick={onBack}>
        ← Back to Dashboard
      </button>

      {/* =====================================================
          HERO
          ===================================================== */}

      <section className="case-timeline-hero">
        <div className="case-timeline-hero-glow" />

        <div className="case-timeline-hero-content">
          <div className="case-timeline-eyebrow">
            <span>◷</span>
            NYAYMITRA CASE TIMELINE
          </div>

          <h1>
            Track your case
            <br />
            <span>journey clearly</span>
          </h1>

          <p>
            Choose one of your saved cases to see its important events,
            hearings and stages in the order they happened.
          </p>
        </div>
      </section>

      {/* =====================================================
          CHOOSE A CASE · TIMELINE
          ===================================================== */}

      <section className="case-timeline-main">
        <div className="case-timeline-picker">
          {!selected ? (
            <>
              <div className="case-timeline-search-card">
                <div className="case-timeline-search-heading">
                  <span className="section-label">YOUR CASES</span>

                  <h2>Choose a case to view its timeline</h2>

                  <p>
                    Every timeline is drawn from that case's own record — no
                    number to look up.
                  </p>
                </div>
              </div>

              <OngoingCases
                cases={cases}
                actionLabel="View Timeline"
                onAction={show}
                busyCnr={busyCnr}
                emptyTitle="No saved cases on this account"
                emptyBody="A timeline is drawn from the case's own record, whether it is still running or finished. Search a CNR in My Cases, save the case, and it will appear here."
              />
            </>
          ) : (
            <section className="case-timeline-result">
              {/* CASE SUMMARY */}

              <div className="case-timeline-summary">
                <div>
                  <span className="section-label">CASE OPENED</span>

                  <h2>Case Timeline</h2>

                  <p>
                    Case Number:
                    <strong> {selected.cnr_number}</strong>
                  </p>
                </div>

                <div className="case-status-badge">
                  <span />
                  {selected.current_case_stage}
                </div>
              </div>

              {/* QUICK STATS */}

              <div className="case-timeline-stats">
                <div>
                  <span>CASE STAGE</span>
                  <strong>{selected.current_case_stage}</strong>
                </div>

                <div>
                  <span>EVENTS</span>
                  <strong>{events?.length ?? 0}</strong>
                </div>

                <div>
                  <span>NEXT HEARING</span>
                  <strong>{formatDate(selected.next_hearing_date)}</strong>
                </div>
              </div>

              {/* TIMELINE */}

              <div className="case-timeline-card">
                <div className="case-timeline-heading">
                  <div>
                    <span className="section-label">CASE HISTORY</span>

                    <h2>Your case journey</h2>
                  </div>

                  <span className="timeline-count">
                    {events?.length ?? 0} Events
                  </span>
                </div>

                <div className="case-timeline-list">
                  {events?.map((event, index) => (
                    <div
                      className={`timeline-item ${event.status}`}
                      key={`${event.title}-${index}`}
                    >
                      {events && index < events.length - 1 && (
                        <div className="timeline-line" />
                      )}

                      <div className="timeline-icon">
                        <event.icon size={18} aria-hidden="true" />
                      </div>

                      <div className="timeline-event-content">
                        <div className="timeline-event-top">
                          <span className="timeline-date">{event.date}</span>

                          {event.status === "current" && (
                            <span className="timeline-current">
                              Current Stage
                            </span>
                          )}
                        </div>

                        <h3>{event.title}</h3>

                        <p>{event.description}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* INFORMATION */}

              <div className="case-timeline-info">
                <Sparkles size={14} aria-hidden="true" />

                <div>
                  <strong>What does this mean?</strong>

                  <p>
                    The timeline shows important stages and events recorded
                    for your case. Dates and case stages should always be
                    verified against official court records.
                  </p>
                </div>
              </div>

              {/* ACTIONS */}

              <div className="case-timeline-result-actions">
                <button
                  type="button"
                  className="delay-new-analysis-button"
                  onClick={() => setSelected(null)}
                >
                  View another case
                </button>
              </div>
            </section>
          )}

          {/* DISCLAIMER */}

          <div className="case-timeline-disclaimer">
            <span>ⓘ</span>

            <p>
              <strong>Important:</strong> Case information shown by NyayMitra
              is intended to help you understand your case history. Always
              verify important dates and proceedings with official court
              records.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
