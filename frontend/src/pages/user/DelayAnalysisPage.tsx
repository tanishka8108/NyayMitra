import { useState } from "react";
import { Settings } from "lucide-react";

import OngoingCases from "../../components/OngoingCases";
import { getCasesForUser, getOngoingCasesForUser } from "../../api/caseApi";
import type { Case } from "../../types/case";

import {
  ModelApiError,
  predictDelay,
} from "../../services/modelApi";
import type {
  ModelApiErrorKind,
  PredictDelayResponse,
} from "../../services/modelApi";

/* `wh-pending` (the in-flight row) and `wh-error` (the red
   failure row) are the shared card styles, so this screen uses
   the same vocabulary as Tell Us What Happened rather than
   growing a second copy. */
import "./WhatHappened.css";

/* =========================================================
   DELAY ANALYSIS

   The screen no longer asks for a CNR. It lists the account's
   live matters and puts one action on each, because nobody
   should have to look up a number that the app already holds
   in order to ask a question about their own case.

   Two things are shown, and they are kept apart on purpose.

   THE ESTIMATES come from POST /predict-delay (src/api.py),
   which returns both numbers in a single response: days to the
   next hearing, and days to disposal. Both are labelled as
   estimates, and both are read against closed cases, so the
   real figure for a running case can be shorter.

   THE REASONS below are derived from the record itself — age,
   stage duration, listed dates, hearing count — and are true
   today regardless of what the model says.
   ========================================================= */

type DelayAnalysisPageProps = {
  userId: string;
  onBack: () => void;
};

type Reason = {
  title: string;
  body: string;
};

type Failure = {
  kind: ModelApiErrorKind;
  message: string;
};

const FAILURE_TITLES: Record<ModelApiErrorKind, string> = {
  validation: "Those case details could not be accepted",
  rate_limit: "Too many requests",
  server: "The model could not predict",
  unavailable: "The prediction service is not available",
  network: "The model service could not be reached",
  unknown: "That prediction could not be made",
};

function formatDate(iso: string): string {
  if (!iso) return "not set";

  const parsed = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return iso;

  return parsed.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

/**
 * Reasons read off the record itself.
 *
 * Each one names a field a reader can go and check, so the
 * screen can justify itself before the model exists instead
 * of asserting an outcome it has no basis for.
 */
function deriveReasons(caseData: Case): Reason[] {
  const reasons: Reason[] = [];

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const next = new Date(`${caseData.next_hearing_date}T00:00:00`);
  const hasValidDate = !Number.isNaN(next.getTime());

  const age = caseData.calculated_metrics?.total_case_age_days ?? 0;
  const stageDays =
    caseData.calculated_metrics?.current_stage_duration_days ?? 0;
  const hearings = caseData.case_history_timeline?.length ?? 0;

  if (!caseData.next_hearing_date || !hasValidDate) {
    reasons.push({
      title: "No hearing is listed",
      body: "The record carries no next hearing date. Matters usually sit idle while awaiting a fresh listing.",
    });
  } else if (next < today) {
    reasons.push({
      title: "The last listed date has passed",
      body: `The date on file was ${formatDate(caseData.next_hearing_date)}. Until a new date is entered, nothing can move.`,
    });
  }

  if (stageDays >= 180) {
    reasons.push({
      title: "A long time at the current stage",
      body: `The matter has been at "${caseData.current_case_stage}" for ${stageDays} days.`,
    });
  }

  if (hearings <= 1) {
    reasons.push({
      title: "Few proceedings on record",
      body: "The hearing history holds little more than the filing itself, so there is little to move the matter forward.",
    });
  } else if (stageDays >= 90) {
    reasons.push({
      title: "Hearings spaced widely apart",
      body: `${hearings} proceedings are on record, with the current stage alone having run ${stageDays} days.`,
    });
  }

  if (age >= 365) {
    reasons.push({
      title: "Running past a year",
      body: `The case has been on file for ${age} days, which is longer than most matters of its kind take.`,
    });
  }

  if (reasons.length === 0) {
    reasons.push({
      title: "Nothing in the record points to a hold",
      body: "The listed dates and the current stage are both within a normal range for a matter of this age.",
    });
  }

  return reasons.slice(0, 3);
}

/* A coarse read from the same signals — labelled preliminary on
   screen, because it is a count of warning signs rather than a
   model's output. */
function delayLevel(reasons: Reason[]): {
  label: string;
  tone: string;
} {
  const strong = reasons.filter((reason) =>
    /passed|no hearing|few proceedings|past a year|180/i.test(
      `${reason.title} ${reason.body}`,
    ),
  ).length;

  if (strong >= 3) return { label: "High", tone: "is-high" };
  if (strong >= 2) return { label: "Moderate", tone: "is-mid" };

  return { label: "Low", tone: "is-low" };
}

export default function DelayAnalysisPage({
  userId,
  onBack,
}: DelayAnalysisPageProps) {
  /* Every saved case belongs on My Cases, the timeline and court
     orders — the record readers show the account's whole shelf.
     Only delay prediction is about what happens next in a running
     matter, so it — and it alone — filters to ongoing cases. */
  const saved = getCasesForUser(userId);
  const cases = getOngoingCasesForUser(userId);

  const [selected, setSelected] = useState<Case | null>(null);
  const [busyCnr, setBusyCnr] = useState<string | null>(null);
  const [prediction, setPrediction] =
    useState<PredictDelayResponse | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);

  /*
   * One round trip. /predict-delay answers with BOTH numbers —
   * days to the next hearing and days to disposal — so a single
   * call fills both cards below.
   */
  const run = async (caseData: Case) => {
    if (busyCnr) return;

    setBusyCnr(caseData.cnr_number);
    setPrediction(null);
    setFailure(null);
    setSelected(caseData);

    try {
      setPrediction(
        await predictDelay({
          case_type: caseData.case_type,
          court: caseData.court_name,
          district: caseData.court_district,
          state: caseData.court_state,
        }),
      );
    } catch (caught) {
      const error =
        caught instanceof ModelApiError
          ? caught
          : new ModelApiError(
              caught instanceof Error
                ? caught.message
                : "That prediction could not be made.",
              "unknown",
            );

      setFailure({ kind: error.kind, message: error.message });
    } finally {
      setBusyCnr(null);
    }
  };

  const reset = () => {
    setSelected(null);
    setPrediction(null);
    setFailure(null);
  };

  const reasons = selected ? deriveReasons(selected) : [];
  const level = selected ? delayLevel(reasons) : null;

  return (
    <main className="delay-analysis-page">
      {/* BACK TO DASHBOARD */}
      <button
        type="button"
        className="delay-back-button"
        onClick={onBack}
      >
        ← Back to Dashboard
      </button>

      {/* HERO */}
      <section className="delay-analysis-hero">
        <div className="delay-analysis-hero-glow" />

        <div className="delay-analysis-hero-content">
          <div className="delay-analysis-eyebrow">
            <span>◷</span>
            NYAYMITRA CASE ANALYSIS
          </div>

          <h1>
            Understand your
            <br />
            <span>case delay</span>
          </h1>

          <p>
            Pick one of your ongoing cases to see what the record says about
            how far it has moved, and where it appears to be held up.
          </p>
        </div>
      </section>

      {/* MAIN */}
      <section className="delay-analysis-main">
        {!selected ? (
          /* =========================
             PICK A CASE
             ========================= */
          <>
            <div className="delay-case-picker-head">
              <span className="delay-section-label">
                CASE DELAY ANALYSIS
              </span>

              <h2>Choose a case to predict delay for</h2>

              <p>
                Each prediction is run against that case's own hearing history
                and stage dates.
              </p>
            </div>

            <OngoingCases
              cases={cases}
              actionLabel="Predict Delay"
              onAction={run}
              busyCnr={busyCnr}
              emptyTitle={
                saved.length > 0
                  ? "Every saved case has concluded"
                  : "No ongoing cases on this account"
              }
              emptyBody={
                saved.length > 0
                  ? "Delay can only be predicted while a case is still running, and each case on this account has finished. Save the CNR of a running case in My Cases and it will appear here."
                  : "Delay can only be predicted for a case that is still running. Search a CNR in My Cases, save the case, and it will appear here."
              }
            />
          </>
        ) : (
          /* =========================
             ANALYSIS RESULT
             ========================= */
          <div className="delay-analysis-result">
            {/* RESULT HEADER */}
            <div className="delay-result-header">
              <div>
                <span className="delay-section-label">DELAY ANALYSIS</span>

                <h2>{selected.case_type}</h2>

                <p>
                  Case Number:
                  <strong> {selected.cnr_number}</strong>
                </p>
              </div>

              <div className="delay-status-badge">Analysis Ready</div>
            </div>

            {/* SUMMARY */}
            <div className="delay-summary-card">
              <div className="delay-summary-icon">◷</div>

              <div>
                <span>CASE DELAY STATUS</span>

                <h3>
                  Preliminary read — {level?.label.toLowerCase()} delay signal
                </h3>

                <p>
                  Read from this case's own dates: filed{" "}
                  {formatDate(selected.filing_date)}, currently at{" "}
                  {selected.current_case_stage}, next listed{" "}
                  {formatDate(selected.next_hearing_date)}.
                </p>
              </div>
            </div>

            {/* =================================================
                ESTIMATES — POST /predict-delay

                Both numbers arrive in one response. They are
                estimates, not dates, and they are read against
                closed cases, so a running case may well be
                quicker than this.
                ================================================= */}
            <div className="delay-stat-grid">
              <div className="delay-stat-card">
                <span>ESTIMATED DAYS TO NEXT HEARING</span>

                <strong>
                  {busyCnr
                    ? "…"
                    : prediction
                      ? `${prediction.predicted_next_hearing_days} days`
                      : "—"}
                </strong>

                <small>Estimate — not a scheduled date</small>
              </div>

              <div className="delay-stat-card">
                <span>ESTIMATED DAYS TO DISPOSAL</span>

                <strong>
                  {busyCnr
                    ? "…"
                    : !prediction
                      ? "—"
                      : prediction.predicted_disposal_days === null ||
                          prediction.predicted_disposal_days === undefined
                        ? "Not available"
                        : `${prediction.predicted_disposal_days} days`}
                </strong>

                <small>
                  {prediction &&
                  (prediction.predicted_disposal_days === null ||
                    prediction.predicted_disposal_days === undefined)
                    ? "The disposal model has not been trained yet"
                    : "Estimate — not a scheduled date"}
                </small>
              </div>
            </div>

            {prediction && (
              <div className="delay-model-note">
                <span aria-hidden="true">◷</span>

                <div>
                  <strong>These are estimates</strong>

                  <p>
                    They come from models trained on <em>closed</em> cases, so
                    the real time for a case still running can be{" "}
                    <em>shorter</em> than the figure above. Treat them as a
                    rough indication of how such matters usually run, not as a
                    date the court has fixed.
                  </p>
                </div>
              </div>
            )}

            {busyCnr && (
              <div className="wh-pending">
                Asking the delay model for both estimates…
              </div>
            )}

            {failure && (
              <div className="delay-model-note wh-error">
                <span aria-hidden="true">ⓘ</span>

                <div>
                  <strong>{FAILURE_TITLES[failure.kind]}</strong>

                  <p>{failure.message}</p>
                </div>
              </div>
            )}

            {/* STATS */}
            <div className="delay-stat-grid">
              <div className="delay-stat-card">
                <span>CASE STATUS</span>
                <strong>{selected.current_case_stage}</strong>
                <small>Current case stage</small>
              </div>

              <div className="delay-stat-card">
                <span>AGE ON FILE</span>
                <strong>
                  {selected.calculated_metrics?.total_case_age_days ?? 0} days
                </strong>
                <small>Since filing</small>
              </div>

              <div className="delay-stat-card">
                <span>DELAY LEVEL</span>
                <strong className={level?.tone}>{level?.label}</strong>
                <small>Preliminary assessment</small>
              </div>
            </div>

            {/* POSSIBLE REASONS */}
            <div className="delay-reasons">
              <div className="delay-result-section-heading">
                <span className="delay-section-label">ANALYSIS</span>

                <h3>Why this case may be held up</h3>
              </div>

              <div className="delay-reason-list">
                {reasons.map((reason, index) => (
                  <div className="delay-reason-item" key={reason.title}>
                    <div className="delay-reason-number">
                      {String(index + 1).padStart(2, "0")}
                    </div>

                    <div>
                      <h4>{reason.title}</h4>
                      <p>{reason.body}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* MODEL STATUS */}
            <div className="delay-model-note">
              <span aria-hidden="true"><Settings size={16} /></span>

              <div>
                <strong>How this estimate is produced</strong>

                <p>
                  Both figures come from the delay models in{" "}
                  <code>src/api.py</code>, ranked against other matters of the
                  same kind. The reasons below are separate: they are read
                  straight from this case's own record and are true whether or
                  not a prediction was made.
                </p>
              </div>
            </div>

            {/* NEXT STEP */}
            <div className="delay-next-step-card">
              <div className="delay-next-step-icon">→</div>

              <div>
                <span className="delay-section-label">SUGGESTED NEXT STEP</span>

                <h3>Review the latest case activity</h3>

                <p>
                  Check the latest hearing date, case stage, orders and pending
                  actions before taking further steps.
                </p>
              </div>
            </div>

            {/* ACTIONS */}
            <div className="delay-result-actions">
              <button
                type="button"
                className="delay-new-analysis-button"
                onClick={reset}
              >
                Predict delay for another case
              </button>
            </div>

            {/* DISCLAIMER */}
            <div className="delay-disclaimer">
              <span>ⓘ</span>

              <p>
                <strong>Note:</strong> This is a preliminary analysis intended
                to help users understand possible case delays. It should not be
                treated as legal advice or a final determination of the reason
                for delay.
              </p>
            </div>
          </div>
        )}
      </section>
    </main>
  );
}
