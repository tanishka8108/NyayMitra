import { useMemo, useState } from "react";
import {
  Scale,
  FileText,
  Image as ImageIcon,
  Paperclip,
  MessageSquare,
  Calendar,
} from "lucide-react";

import type { Case } from "../types/case";
import type { ChatTarget } from "../api/chatApi";
import { getGuidance, type GuidanceResult } from "../api/guidanceApi";
import CaseDocumentsSection from "./CaseDocumentsSection";
import {
  DOCUMENT_CATEGORIES,
  addDocument,
  listDocuments,
  readFileAsDataUrl,
  removeDocument,
  type CaseDocument,
  type DocumentCategory,
} from "../api/documentApi";
import { useT } from "../i18n/context";

import "./CaseDetail.css";

/* =========================================================
   MY CASES — ONE MATTER, IN FULL

   The screen behind a case card. It answers the four
   questions a reader actually has about a case they are
   tracking: who is on either side, where and when it is
   next heard, what documents have been added, and how to
   reach the advocate handling it.

   The last one matters most. The assigned lawyer is not a
   name in a footer — it is a button, and it opens the thread
   already scoped to this CNR, so the conversation about the
   matter lives with the matter.
   ========================================================= */

type CaseDetailProps = {
  caseData: Case;

  /* Account viewing the file. Documents uploaded here are
     stamped with it, which is what keeps the citizen's copy
     and the lawyer's view distinguishable later. */
  userId: string;

  onBack: () => void;

  /* Opens a chat thread. Omitted where the screen has no
     chat — the component then simply does not offer one
     rather than showing a button that goes nowhere. */
  onChat?: (target: ChatTarget) => void;

  /* Hands the reader to the Court Orders screen, where the existing
     extraction/explanation service lives. Omitted where the shell has
     no such door, and then the order cards carry no button at all. */
  onOpenCourtOrders?: () => void;
};

function formatDate(iso: string): string {
  if (!iso) return "—";

  const parsed = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return iso;

  return parsed.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

/* The right glyph for a stored document — a pure function of the
   mime type, returning an element so nothing is created during
   render (react-hooks/static-components). */
function documentIcon(mime: string) {
  if (mime.startsWith("image/")) {
    return <ImageIcon size={16} />;
  }
  if (mime === "application/pdf") {
    return <FileText size={16} />;
  }
  return <Paperclip size={16} />;
}

/* A date the court has not reached yet. An empty or unparseable date
   is never "upcoming" — it is simply unknown, and the timeline says
   so rather than guessing. */
function isFuture(iso: string): boolean {
  if (!iso) return false;

  const parsed = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return false;

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  return parsed >= today;
}

/* =========================================================
   DOCUMENT ROW
   ========================================================= */

function DocumentRow({
  document,
  expanded,
  onToggle,
  onRemove,
}: {
  document: CaseDocument;
  expanded: boolean;
  onToggle: () => void;
  onRemove: () => void;
}) {
  const { t } = useT();

  const previewable = document.dataUrl !== null;

  return (
    <li className="matter-doc">
      <div className="matter-doc-line">
        <span className="matter-doc-icon" aria-hidden="true">
          {documentIcon(document.mime)}
        </span>

        <div className="matter-doc-meta">
          <strong title={document.name}>{document.name}</strong>

          <span>
            {t(CATEGORY_KEYS[document.category] ?? document.category)} ·{" "}
            {formatBytes(document.size)} ·{" "}
            {formatDate(document.uploadedAt.slice(0, 10))}
          </span>
        </div>

        <div className="matter-doc-actions">
          {previewable ? (
            <button type="button" className="doc-ghost" onClick={onToggle}>
              {expanded ? t("detail.doc.hide") : t("detail.doc.preview")}
            </button>
          ) : (
            <span className="doc-muted">{t("detail.doc.recordOnly")}</span>
          )}

          <button
            type="button"
            className="doc-ghost doc-ghost-danger"
            onClick={onRemove}
          >
            {t("detail.doc.remove")}
          </button>
        </div>
      </div>

      {expanded && previewable && (
        <div className="matter-doc-preview">
          {document.mime.startsWith("image/") ? (
            <img src={document.dataUrl ?? ""} alt={document.name} />
          ) : (
            <object
              data={document.dataUrl ?? ""}
              type={document.mime}
              aria-label={document.name}
            >
              <a href={document.dataUrl ?? ""} download={document.name}>
                {t("detail.doc.open")} {document.name}
              </a>
            </object>
          )}
        </div>
      )}

      {!previewable && document.note && (
        <p className="matter-doc-note">{document.note}</p>
      )}
    </li>
  );
}

/* =========================================================
   CATEGORY LABELS

   Display-only keys for the stored category values — the value
   stored on the document is never changed, only the words
   shown for it.
   ========================================================= */

const CATEGORY_KEYS: Record<string, string> = {
  Filing: "detail.cat.filing",
  Evidence: "detail.cat.evidence",
  Identity: "detail.cat.identity",
  "Court order": "detail.cat.courtOrder",
  Correspondence: "detail.cat.correspondence",
  Other: "detail.cat.other",
};

/* =========================================================
   MAIN
   ========================================================= */

export default function CaseDetail({
  caseData,
  userId,
  onBack,
  onChat,
  onOpenCourtOrders,
}: CaseDetailProps) {
  const { t } = useT();

  const cnr = caseData.cnr_number;

  const [documents, setDocuments] = useState<CaseDocument[]>(() =>
    listDocuments(cnr),
  );
  const [category, setCategory] = useState<DocumentCategory>("Evidence");
  const [uploading, setUploading] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

  /* -------------------------------------------------
     NEXT STEPS — the guidance service the dashboard and the
     voice screen already call, asked from where this matter
     stands. The question is assembled only from values this
     record carries: nothing about the case is invented to
     make a tidier prompt.
     ------------------------------------------------- */
  const [guidance, setGuidance] = useState<GuidanceResult | null>(null);
  const [guidanceBusy, setGuidanceBusy] = useState(false);
  const [guidanceError, setGuidanceError] = useState("");

  async function askGuidance() {
    const parts = [
      caseData.case_status,
      caseData.current_case_stage
        ? `Current stage: ${caseData.current_case_stage}`
        : "",
      caseData.next_hearing_date
        ? `Next hearing ${formatDate(caseData.next_hearing_date)}`
        : "",
      caseData.case_type ? `Case type: ${caseData.case_type}` : "",
    ].filter((part): part is string => Boolean(part));

    setGuidanceBusy(true);
    setGuidanceError("");
    setGuidance(null);

    try {
      setGuidance(await getGuidance(parts.join(". ") + "."));
    } catch {
      setGuidanceError(
        t("detail.guidance.error"),
      );
    } finally {
      setGuidanceBusy(false);
    }
  }

  const refresh = () => {
    setDocuments(listDocuments(cnr));
    setExpanded(null);
  };

  async function handleUpload(
    event: React.ChangeEvent<HTMLInputElement>,
  ) {
    const input = event.target;
    const files = Array.from(input.files ?? []);

    if (files.length === 0) return;

    setUploading(true);

    try {
      for (const file of files) {
        const dataUrl = await readFileAsDataUrl(file);

        addDocument({
          cnr,
          owner_user_id: userId,
          category,
          file,
          dataUrl,
        });
      }

      refresh();
    } finally {
      setUploading(false);
      input.value = "";
    }
  }

  const lawyerName =
    caseData.petitioner_advocate ||
    (caseData.handling_lawyer_id ? t("detail.assignedAdvocate") : "");

  /* The chat door. Present only when the matter actually has an
     advocate on it — a case tracked without one has nobody to
     message, and pretending otherwise would produce a thread
     with an unknown party on the other end. */
  const canChat =
    Boolean(onChat) && Boolean(caseData.handling_lawyer_id);

  const openLawyerChat = () => {
    if (!canChat || !onChat) return;

    onChat({
      id: caseData.handling_lawyer_id,
      name: lawyerName,
      role: "LAWYER",
      caseCnr: cnr,
    });
  };

  const metrics = caseData.calculated_metrics;

  const groupedHistory = useMemo(
    () => caseData.case_history_timeline ?? [],
    [caseData.case_history_timeline],
  );

  /* The whole journey as the case service orders it — filing,
     registration, sittings, orders, the next date, oldest first.
     Absent for cases saved from the browser's store, which have
     no court record behind them and fall back to their hearing
     list above. */
  const journey = caseData.timeline ?? [];

  return (
    <section className="matter-detail">
      {/* -------------------------------------------------
          HEADER
          ------------------------------------------------- */}
      <div className="matter-head">
        <button type="button" className="matter-back" onClick={onBack}>
          {t("cases.allCases")}
        </button>

        <div className="matter-head-main">
          <div>
            <span className="matter-eyebrow">{t("cases.label.cnr")}</span>
            <h2>{cnr}</h2>
            <p className="matter-type">
              {caseData.case_type} · {t("cases.filed")} {formatDate(caseData.filing_date)}
            </p>
          </div>

          <div className="matter-head-side">
            {/* Where the matter stands in court terms, and the
                status the source records for it — a pending case
                and a disposed one read differently at a glance. */}
            <span className="matter-stage">{caseData.current_case_stage}</span>

            {caseData.case_status && (
              <span
                className={`matter-status${
                  /disposed/i.test(caseData.case_status)
                    ? " matter-status-disposed"
                    : " matter-status-pending"
                }`}
              >
                {caseData.case_status}
              </span>
            )}

            {canChat && (
              <button
                type="button"
                className="matter-chat-btn"
                onClick={openLawyerChat}
              >
                <MessageSquare size={14} aria-hidden="true" />
                {t("detail.chat")}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* -------------------------------------------------
          SOURCE

          A record read from the case service says where it came
          from and, more importantly, what it is not: this is a
          development dataset, not a live eCourts feed. Showing
          that once, under the header, beats letting a reader
          assume every number here is the court's today.
          ------------------------------------------------- */}
      {caseData.data_source && (
        <p className="matter-source">
          <span className="matter-source-tag">
            {caseData.data_source.live_ecourts_data
              ? t("detail.source.live")
              : t("detail.source.dev")}
          </span>

          <span>
            <strong>{caseData.data_source.label}.</strong>{" "}
            {caseData.data_source.disclaimer}
          </span>
        </p>
      )}

      {/* -------------------------------------------------
          PARTIES · COURT · SCHEDULE
          ------------------------------------------------- */}
      <div className="matter-grid">
        <article className="matter-card">
          <h3>{t("detail.parties")}</h3>

          <div className="matter-parties">
            <div className="matter-party">
              <span className="detail-label">{t("cases.label.petitioner")}</span>
              <strong>{caseData.petitioner_name}</strong>
            </div>

            <div className="matter-party-arrow" aria-hidden="true">
              →
            </div>

            <div className="matter-party">
              <span className="detail-label">{t("cases.label.respondents")}</span>
              <strong>{caseData.respondents_list.join(", ")}</strong>
            </div>
          </div>

          <dl className="matter-fields">
            <div>
              <dt>{t("detail.petAdvocate")}</dt>
              <dd>{caseData.petitioner_advocate || "—"}</dd>
            </div>

            <div>
              <dt>{t("detail.actApplied")}</dt>
              <dd>
                {caseData.applied_act}
                {caseData.applied_section
                  ? t("detail.section", { n: caseData.applied_section })
                  : ""}
              </dd>
            </div>
          </dl>
        </article>

        <article className="matter-card">
          <h3>{t("detail.court")}</h3>

          <dl className="matter-fields">
            <div>
              <dt>{t("detail.court")}</dt>
              <dd>{caseData.court_name}</dd>
            </div>

            <div>
              <dt>{t("detail.district")}</dt>
              <dd>
                {caseData.court_district}, {caseData.court_state}
              </dd>
            </div>

            <div>
              <dt>{t("detail.presidingJudge")}</dt>
              <dd>{caseData.presiding_judge || t("detail.notListed")}</dd>
            </div>

            <div>
              <dt>{t("detail.filingNumber")}</dt>
              <dd>{caseData.filing_number || "—"}</dd>
            </div>
          </dl>
        </article>

        <article className="matter-card">
          <h3>{t("detail.schedule")}</h3>

          <div className="matter-hearing">
            <span className="detail-label">{t("cases.label.nextHearing")}</span>
            <strong>{formatDate(caseData.next_hearing_date)}</strong>
          </div>

          <dl className="matter-fields">
            <div>
              <dt>{t("detail.firstHearing")}</dt>
              <dd>{formatDate(caseData.first_hearing_date)}</dd>
            </div>

            <div>
              <dt>{t("detail.registrationDate")}</dt>
              <dd>{formatDate(caseData.registration_date)}</dd>
            </div>
          </dl>

          {metrics && (
            <div className="matter-stats">
              <div>
                <strong>{metrics.total_case_age_days}</strong>
                <span>{t("detail.daysOnFile")}</span>
              </div>

              <div>
                <strong>{metrics.respondent_count}</strong>
                <span>
                  {metrics.respondent_count === 1
                    ? t("detail.respondent.one")
                    : t("detail.respondent.other")}
                </span>
              </div>

              <div>
                <strong>{metrics.current_stage_duration_days}</strong>
                <span>{t("detail.daysAtStage")}</span>
              </div>
            </div>
          )}

          {/* -------------------------------------------------
              NEXT STEPS — the guidance service the dashboard and
              the voice screen already use, asked from this record's
              own status, stage and listing.
              ------------------------------------------------- */}
          <div className="matter-guidance">
            <button
              type="button"
              className="matter-guidance-btn"
              onClick={askGuidance}
              disabled={guidanceBusy}
            >
              {guidanceBusy ? t("detail.guidance.asking") : t("detail.guidance.ask")}
            </button>

            {guidanceError && (
              <p className="matter-guidance-error">{guidanceError}</p>
            )}

            {guidance && (
              <div className="matter-guidance-result">
                {guidance.matched && guidance.stage ? (
                  <p className="matter-guidance-stage">
                    <strong>{guidance.stage}</strong>
                    {guidance.urgency ? <> · {guidance.urgency}</> : null}
                  </p>
                ) : null}

                <p>{guidance.matched ? guidance.what_to_do_next : guidance.why}</p>

                <p className="matter-guidance-note">{guidance.disclaimer}</p>
              </div>
            )}
          </div>
        </article>
      </div>

      {/* -------------------------------------------------
          DOCUMENTS
          ------------------------------------------------- */}
      <article className="matter-card matter-documents">
        <div className="matter-card-head">
          <div>
            <h3>{t("detail.docs.title")}</h3>
            <p>{t("detail.docs.copy")}</p>
          </div>
        </div>

        <div className="matter-upload">
          <select
            value={category}
            onChange={(event) =>
              setCategory(event.target.value as DocumentCategory)
            }
            aria-label={t("detail.docs.categoryAria")}
          >
            {DOCUMENT_CATEGORIES.map((item) => (
              <option key={item} value={item}>
                {t(CATEGORY_KEYS[item] ?? item)}
              </option>
            ))}
          </select>

          <label className="matter-upload-btn">
            {uploading ? t("detail.docs.uploading") : t("detail.docs.add")}

            <input
              type="file"
              multiple
              onChange={handleUpload}
              disabled={uploading}
            />
          </label>
        </div>

        {documents.length > 0 ? (
          <ul className="matter-doc-list">
            {documents.map((document) => (
              <DocumentRow
                key={document.id}
                document={document}
                expanded={expanded === document.id}
                onToggle={() =>
                  setExpanded((current) =>
                    current === document.id ? null : document.id,
                  )
                }
                onRemove={() => {
                  removeDocument(document.id);
                  refresh();
                }}
              />
            ))}
          </ul>
        ) : (
          <div className="matter-empty">
            <span aria-hidden="true"><Paperclip size={18} /></span>
            <p>{t("detail.docs.empty")}</p>
          </div>
        )}
      </article>

      {/* -------------------------------------------------
          ORDERS THE COURT HAS PASSED

          Distinct from the documents above: those are files this
          account added, these are the court's own record of what
          it has ruled. Cases opened from the browser's store have
          no such record, and the card is simply not rendered for
          them rather than appearing empty.
          ------------------------------------------------- */}
      {/* -------------------------------------------------
          ORDERS THE COURT HAS PASSED

          Distinct from the documents above: those are files this
          account added, these are the court's own record of what
          it has ruled.

          A record read from the case service always gets this card,
          including when nothing has been passed — "no orders yet" is
          an answer, and a blank is not. Cases opened from the
          browser's store keep the old behaviour and get no card.

          The docket entry is all the capture holds; the document
          itself is not in the dataset. So the action offered is the
          one that exists: hand the reader to Court Orders, where the
          extraction and explanation service reads a pasted or
          uploaded copy.
          ------------------------------------------------- */}
      {(caseData.data_source || (caseData.orders?.length ?? 0) > 0) && (
        <article className="matter-card matter-orders">
          <div className="matter-card-head">
            <div>
              <h3>{t("detail.orders.title")}</h3>
              <p>{t("detail.orders.copy")}</p>
            </div>
          </div>

          {(caseData.orders?.length ?? 0) === 0 ? (
            <div className="matter-empty">
              <span aria-hidden="true"><Scale size={18} /></span>
              <p>{t("detail.orders.empty")}</p>
            </div>
          ) : (
            <ul className="matter-order-list">
              {caseData.orders?.map((order, index) => (
                <li key={`${order.order_number}_${index}`}>
                  <div className="matter-order-line">
                    <strong>
                      {order.order_type} {t("detail.orders.no", { n: order.order_number || "—" })}
                    </strong>

                    <span className="matter-order-date">
                      {formatDate(order.order_date)}
                    </span>
                  </div>

                  <span className="matter-order-section">
                    {order.order_section}
                  </span>

                  {order.order_details && <p>{order.order_details}</p>}

                  {onOpenCourtOrders && (
                    <div className="matter-order-actions">
                      <button
                        type="button"
                        className="doc-ghost"
                        onClick={onOpenCourtOrders}
                      >
                        {t("detail.orders.explain")}
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </article>
      )}

      {/* -------------------------------------------------
          COURT DOCUMENTS — actual files from the case service
          (contract in caseDocumentApi). Rendered only for
          service-backed records: a case saved in this browser
          has no court service behind it, so there is nothing
          to fetch and the section does not appear.
          ------------------------------------------------- */}
      <CaseDocumentsSection
        cnr={cnr}
        enabled={Boolean(caseData.data_source)}
      />

      {/* -------------------------------------------------
          TIMELINE

          The case service returns the whole journey already in
          order — filed, registered, every sitting, every order, the
          next date — so a service record shows that. Cases saved
          from the browser's store have no court record to draw a
          journey from and keep their hearing list, in the same
          shape.
          ------------------------------------------------- */}
      <article className="matter-card">
        <div className="matter-card-head">
          <div>
            <h3>
              {journey.length > 0
                ? t("detail.timeline.title")
                : t("detail.timeline.history")}
            </h3>

            <p>
              {journey.length > 0
                ? t("detail.timeline.intro")
                : t("detail.timeline.introHistory")}
            </p>
          </div>
        </div>

        {journey.length > 0 ? (
          <ol className="matter-timeline">
            {journey.map((step, index) => {
              const upcoming = isFuture(step.date);

              return (
                <li
                  key={`${step.date}_${step.event}_${index}`}
                  className={[
                    upcoming ? "is-upcoming" : "",
                    step.event === "Next hearing" ? "is-next" : "",
                    step.event === "Case filed" ||
                    step.event === "Case registered"
                      ? "is-milestone"
                      : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                >
                  <span className="matter-timeline-date">
                    {step.date
                      ? formatDate(step.date)
                      : t("detail.timeline.noDate")}
                  </span>

                  <div>
                    <strong>{step.event}</strong>
                    {step.description && <span>{step.description}</span>}
                  </div>
                </li>
              );
            })}
          </ol>
        ) : groupedHistory.length > 0 ? (
          <ol className="matter-timeline">
            {groupedHistory.map((entry, index) => (
              <li key={`${entry.hearing_date}_${index}`}>
                <span className="matter-timeline-date">
                  {formatDate(entry.hearing_date)}
                </span>

                <div>
                  <strong>{entry.purpose_of_hearing}</strong>
                  <span>{entry.judge_title}</span>
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <div className="matter-empty">
            <span aria-hidden="true"><Calendar size={18} /></span>
            <p>{t("detail.timeline.empty")}</p>
          </div>
        )}
      </article>
    </section>
  );
}
