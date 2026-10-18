import { useState } from "react";
import {
  ClipboardList,
  Calendar,
  NotebookPen,
  CircleCheck,
  FileText,
  Scale,
  MessageSquare,
  ChartColumn,
  TriangleAlert,
  FolderOpen,
  ShieldCheck,
  Lock,
  Check,
  Circle,
} from "lucide-react";
import type { Session } from "../../auth/session";
import type { Page } from "../../App";
import {
  AUTHORITY_CATALOG,
  authoritiesByCategory,
  getAuthoritiesFor,
  getWorkFor,
  workById,
} from "../../api/authorityApi";
import {
  getLawyerById,
  getLawyers,
  setLawyerVerification,
} from "../../api/lawyerApi";
import type {
  Lawyer,
  VerificationState,
} from "../../api/lawyerApi";
import RoleDashboardShell, {
  type DashboardSection,
  type DashboardStat,
} from "../../components/RoleDashboardShell";
import RoleSectionView from "../../components/RoleSectionView";
import { initialsOf } from "../../lib/initials";
import { getCases } from "../../api/caseApi";
import { STAFF_TASKS, STAFF_DOCUMENTS } from "../../mocks/staffWork";
import "../../components/RoleDashboardShell.css";
import "../../components/RoleSectionView.css";
import "./StaffDashboardPage.css";

/* =========================================================
   STAFF DASHBOARD

   Authorized operational / case-management work carried
   out under the admin role.

   Staff accounts are issued by the admin, and staff sign
   in through the admin login door (see LoginPage).

   Every section below is a planned screen; the shell
   itself is ready and identical in structure to the other
   three dashboards.

   What this account may actually do is whatever the
   administrator delegated on the Access & Roles screen.
   The communication section only opens if that authority
   was granted, so a revoked grant shows up here instead of
   merely going unenforced. See chatApi for who staff may
   talk to once the inbox is open.
   ========================================================= */

type StaffDashboardPageProps = {
  session: Session;
  onSignOut: () => void;
  onNavigate: (page: Page) => void;
};

/* =====================================================
   DATE HELPERS
   ===================================================== */

function formatDay(iso: string): string {
  const parsed = new Date(`${iso}T00:00:00`);

  if (Number.isNaN(parsed.getTime())) return iso;

  return parsed.toLocaleDateString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function daysFromToday(iso: string): number | null {
  const target = new Date(`${iso}T00:00:00`).getTime();

  if (Number.isNaN(target)) return null;

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  return Math.round((target - today.getTime()) / 86_400_000);
}

function StaffDashboardPage({
  session,
  onSignOut,
  onNavigate,
}: StaffDashboardPageProps) {
  /* =====================================================
     CONFIG
     ===================================================== */

  const granted = getAuthoritiesFor(session.userId);

  /* Acknowledges the (mock) report submission without
     pretending a network call happened. */
  const [reportSent, setReportSent] = useState(false);

  const has = (authorityId: string) =>
    granted.includes(authorityId);

  /* Which inline screen, if any, is open. Mirrors the admin
     dashboard's activeSection so both roles behave the same. */
  const [activeSection, setActiveSection] =
    useState<string | null>(null);

  /* =====================================================
     LAWYER VERIFICATION

     Staff reach this through the same door the admin does,
     and it only appears when lawyers.verify has been
     granted — the card says so rather than opening and
     failing.

     The directory comes from the lawyer service; each row
     is resolved through the detail endpoint because that
     is the only place verification status exists.
     ===================================================== */

  const [lawyerList, setLawyerList] = useState<Lawyer[]>([]);

  /* "idle" until the card is opened, so a failure can be retried
     without the guard that stops a double-fetch swallowing the
     second attempt. */
  const [lawyerStatus, setLawyerStatus] = useState<
    "idle" | "pending" | "ready" | "error"
  >("idle");

  const loadLawyerRecords = () => {
    if (lawyerStatus === "pending" || lawyerStatus === "ready") return;

    setLawyerStatus("pending");

    void (async () => {
      try {
        const page = await getLawyers({ page: 1, limit: 20 });

        const resolved = await Promise.all(
          page.lawyers.map(async (summary) => {
            try {
              return await getLawyerById(summary.lawyer_id);
            } catch {
              return summary;
            }
          }),
        );

        setLawyerList(resolved);
        setLawyerStatus("ready");
      } catch {
        setLawyerStatus("error");
      }
    })();
  };

  const decideVerification = (
    lawyerId: string,
    state: VerificationState,
  ) => {
    setLawyerVerification(lawyerId, state);

    setLawyerList((previous) =>
      previous.map((item) =>
        item.lawyer_id === lawyerId
          ? { ...item, profile_status: state }
          : item,
      ),
    );
  };

  /* The work the administrator assigned this account, if any. */
  const myWork = workById(getWorkFor(session.userId));

  /* =====================================================
     WORKLIST FIGURES

     Counted from the same fixtures the screens below read,
     so the header can never claim a number the list does
     not then show.
     ===================================================== */

  const todayIso = new Date().toISOString().slice(0, 10);

  /* Seeded matters plus any the citizens filed since. Read
     once here so the header, the lists and the reports below
     all count the same set rather than re-reading storage at
     each use site. */
  const allCases = getCases();

  const upcomingHearings = allCases.filter(
    (item) => item.next_hearing_date >= todayIso,
  );

  const openTasks = STAFF_TASKS.filter(
    (task) => task.status !== "Done",
  );

  const stats: DashboardStat[] = [
    {
      icon: ClipboardList,
      tone: "purple",
      label: "CASES ON FILE",
      value: String(allCases.length),
      detail: "Records you may update",
    },
    {
      icon: Calendar,
      tone: "blue",
      label: "HEARINGS AHEAD",
      value: String(upcomingHearings.length),
      detail: "Still to be held",
    },
    {
      icon: NotebookPen,
      tone: "orange",
      label: "OPEN TASKS",
      value: String(openTasks.length),
      detail: "Assigned by admin",
    },
    {
      icon: CircleCheck,
      tone: "green",
      label: "STATUS",
      value: "Active",
      detail: "Authorized by admin",
    },
  ];

  /* =====================================================
     AUTHORITY GATE

     Each staff section corresponds to exactly one authority
     (see AUTHORITY_CATALOG). Not holding it means the card
     says so rather than opening and failing.
     ===================================================== */

  const gated = (
    authorityId: string,
    onOpen: () => void,
  ): Pick<
    DashboardSection,
    "status" | "badge" | "cta" | "onOpen"
  > =>
    has(authorityId)
      ? { status: "ready", badge: "Open", onOpen }
      : {
          status: "planned",
          badge: "Not granted",
          cta: "Ask the administrator for access",
          onOpen,
        };

  const sections: DashboardSection[] = [
    {
      id: "caseFiles",
      icon: ClipboardList,
      title: "Case Files",
      description:
        "Operational case management: update case records, " +
        "attach documents and track filing status.",
      ...gated("cases.update", () =>
        setActiveSection("caseFiles"),
      ),
    },
    {
      id: "hearings",
      icon: Calendar,
      title: "Hearings & Court Activities",
      description:
        "View upcoming hearings, cause lists and court " +
        "activities for assigned cases.",
      ...gated("hearings.view", () =>
        setActiveSection("hearings"),
      ),
    },
    {
      id: "documents",
      icon: FileText,
      title: "Document Processing",
      description:
        "Upload and process court orders and case " +
        "documents through OCR and PDF pipelines.",
      ...gated("documents.process", () =>
        setActiveSection("documents"),
      ),
    },
    {
      id: "lawyers",
      icon: Scale,
      title: "Lawyer Verification",
      description: has("lawyers.verify")
        ? "Confirm or reject an advocate's registration " +
          "papers — the same ruling the admin makes."
        : "Verification authority has not been granted to " +
          "this account. The administrator can grant it " +
          "under Access & Roles.",
      ...gated("lawyers.verify", () => {
        loadLawyerRecords();
        setActiveSection("lawyers");
      }),
    },
    {
      id: "communication",
      icon: MessageSquare,
      title: "Client Communication",
      description: has("messages.send")
        ? "Handle authorized communication with users and " +
          "lawyers on assigned matters, and with the admin."
        : "Messaging authority has not been granted to this " +
          "account. The administrator can restore it under " +
          "Access & Roles.",
      ...gated("messages.send", () => onNavigate("chat")),
    },
    {
      id: "tasks",
      icon: NotebookPen,
      title: "Task Queue",
      description:
        "Work through tasks assigned by the administrator, " +
        "with priority and due-date tracking.",
      status: "ready",
      badge: "Open",
      onOpen: () => setActiveSection("tasks"),
    },
    {
      id: "reports",
      icon: ChartColumn,
      title: "Operational Reports",
      description:
        "Daily activity summaries submitted to the " +
        "administrator for review.",
      ...gated("reports.submit", () =>
        setActiveSection("reports"),
      ),
    },
  ];

  /* =====================================================
     CASE FILES
     ===================================================== */

  if (activeSection === "caseFiles") {
    return (
      <RoleSectionView
        session={session}
        portal="NYAYMITRA STAFF PORTAL"
        title="Case"
        titleAccent="files."
        heroDescription="Every matter you are authorized to update, with its parties, current stage and hearing date."
        workspaceTitle="Update case records"
        workspaceSubtitle="Filed under admin authority"
        onBack={() => setActiveSection(null)}
      >
        <div className="section-stats">

          <div className="section-stat">
            <span>ON FILE</span>
            <strong>{allCases.length}</strong>
            <small>Records you may edit</small>
          </div>

          <div className="section-stat">
            <span>WITH A DATE</span>
            <strong>{upcomingHearings.length}</strong>
            <small>Next hearing set</small>
          </div>

          <div className="section-stat">
            <span>STAGES</span>
            <strong>
              {
                new Set(
                  allCases.map((item) => item.current_case_stage),
                ).size
              }
            </strong>
            <small>Distinct stages</small>
          </div>

        </div>

        <div className="section-card">

          <span className="role-dashboard-section-label">
            ALL MATTERS
          </span>

          <h3>Records you may update</h3>

          <p>
            Edits made here become part of the case record and are
            attributable to this staff account, which is why the
            authority to make them is granted rather than assumed.
          </p>

          <ul className="section-rows">
            {allCases.map((item) => (
              <li key={item.cnr_number} className="section-row">

                <span className="section-row-avatar">
                  {initialsOf(item.petitioner_name)}
                </span>

                <div className="section-row-body">
                  <strong>{item.petitioner_name}</strong>
                  <span>
                    {item.cnr_number} · {item.court_name} ·{" "}
                    {item.respondents_list.length} respondent
                    {item.respondents_list.length === 1 ? "" : "s"}
                  </span>
                </div>

                <div className="section-row-meta">
                  <time>{formatDay(item.next_hearing_date)}</time>
                  <span className="section-pill info">
                    {item.current_case_stage}
                  </span>
                </div>

              </li>
            ))}
          </ul>

        </div>
      </RoleSectionView>
    );
  }

  /* =====================================================
     HEARINGS & COURT ACTIVITIES
     ===================================================== */

  if (activeSection === "hearings") {
    const sorted = [...upcomingHearings].sort((a, b) =>
      a.next_hearing_date.localeCompare(b.next_hearing_date),
    );

    const recent = allCases
      .flatMap((item) =>
        item.case_history_timeline.map((entry) => ({
          cnr: item.cnr_number,
          court: item.court_name,
          ...entry,
        })),
      )
      .sort((a, b) => b.hearing_date.localeCompare(a.hearing_date))
      .slice(0, 5);

    return (
      <RoleSectionView
        session={session}
        portal="NYAYMITRA STAFF PORTAL"
        title="Hearings &"
        titleAccent="court activities."
        heroDescription="What is still to be held, ordered by date, and the five hearings most recently concluded."
        workspaceTitle="Track the hearing list"
        workspaceSubtitle="Dates read from the case records"
        onBack={() => setActiveSection(null)}
      >
        <div className="section-stats">

          <div className="section-stat">
            <span>UPCOMING</span>
            <strong>{sorted.length}</strong>
            <small>Not yet held</small>
          </div>

          <div className="section-stat">
            <span>NEXT UP</span>
            <strong>
              {sorted[0] ? formatDay(sorted[0].next_hearing_date) : "—"}
            </strong>
            <small>
              {sorted[0] && daysFromToday(sorted[0].next_hearing_date) !== null
                ? `In ${daysFromToday(sorted[0].next_hearing_date)} day${
                    daysFromToday(sorted[0].next_hearing_date) === 1 ? "" : "s"
                  }`
                : "Nothing scheduled"}
            </small>
          </div>

          <div className="section-stat">
            <span>CONCLUDED</span>
            <strong>
              {allCases.reduce(
                (sum, item) => sum + item.case_history_timeline.length,
                0,
              )}
            </strong>
            <small>On record</small>
          </div>

        </div>

        <div className="section-card">

          <span className="role-dashboard-section-label">
            UPCOMING
          </span>

          <h3>Still to be held</h3>

          <p>
            Cause lists are published by the court, not by this system —
            these are the dates already recorded against each matter.
          </p>

          {sorted.length === 0 ? (
            <div className="section-empty">
              <span aria-hidden="true"><Calendar size={16} /></span>
              <p>No hearings are scheduled. New dates will appear here.</p>
            </div>
          ) : (
            <ul className="section-rows">
              {sorted.map((item) => {
                const days = daysFromToday(item.next_hearing_date);

                return (
                  <li key={item.cnr_number} className="section-row">

                    <span className="section-row-avatar" aria-hidden="true">
                      <Scale size={15} />
                    </span>

                    <div className="section-row-body">
                      <strong>{item.petitioner_name}</strong>
                      <span>
                        {item.cnr_number} · {item.presiding_judge}
                      </span>
                    </div>

                    <div className="section-row-meta">
                      <time>{formatDay(item.next_hearing_date)}</time>
                      <span
                        className={`section-pill ${
                          days !== null && days <= 14 ? "warn" : "info"
                        }`}
                      >
                        {days !== null && days >= 0
                          ? `in ${days} day${days === 1 ? "" : "s"}`
                          : "date set"}
                      </span>
                    </div>

                  </li>
                );
              })}
            </ul>
          )}

          <span className="role-dashboard-section-label section-sublabel">
            RECENTLY CONCLUDED
          </span>

          <ul className="section-rows section-sublabel-list">
            {recent.map((entry, index) => (
              <li
                key={`${entry.cnr}-${entry.hearing_date}-${index}`}
                className="section-row"
              >
                <span className="section-row-avatar" aria-hidden="true">
                  <Check size={14} />
                </span>

                <div className="section-row-body">
                  <strong>{entry.purpose_of_hearing}</strong>
                  <span>
                    {entry.cnr} · {entry.judge_title}
                  </span>
                </div>

                <div className="section-row-meta">
                  <time>{formatDay(entry.hearing_date)}</time>
                </div>
              </li>
            ))}
          </ul>

        </div>
      </RoleSectionView>
    );
  }

  /* =====================================================
     DOCUMENT PROCESSING
     ===================================================== */

  if (activeSection === "documents") {
    const pipelinePill: Record<string, string> = {
      Filed: "good",
      Translated: "good",
      "OCR complete": "info",
      "Awaiting OCR": "warn",
    };

    return (
      <RoleSectionView
        session={session}
        portal="NYAYMITRA STAFF PORTAL"
        title="Document"
        titleAccent="processing."
        heroDescription="Court orders, statements and affidavits running through the OCR and translation pipeline."
        workspaceTitle="Process case documents"
        workspaceSubtitle="Gated on documents.process"
        onBack={() => setActiveSection(null)}
      >
        <div className="section-stats">

          <div className="section-stat">
            <span>IN QUEUE</span>
            <strong>{STAFF_DOCUMENTS.length}</strong>
            <small>Documents on file</small>
          </div>

          <div className="section-stat">
            <span>AWAITING OCR</span>
            <strong>
              {
                STAFF_DOCUMENTS.filter(
                  (doc) => doc.pipeline === "Awaiting OCR",
                ).length
              }
            </strong>
            <small>Not yet read</small>
          </div>

          <div className="section-stat">
            <span>PAGES</span>
            <strong>
              {STAFF_DOCUMENTS.reduce((sum, doc) => sum + doc.pages, 0)}
            </strong>
            <small>Across the queue</small>
          </div>

        </div>

        <div className="section-card">

          <span className="role-dashboard-section-label">
            PROCESSING QUEUE
          </span>

          <h3>Documents and where they are in the pipeline</h3>

          <p>
            OCR and translation run on the NLP service, so a document sits
            in “Awaiting OCR” until that service is up. Upload itself
            lands with the document API, which is still pending.
          </p>

          <ul className="section-rows">
            {STAFF_DOCUMENTS.map((doc) => (
              <li key={doc.id} className="section-row">

                <span className="section-row-avatar" aria-hidden="true">
                  <FileText size={14} />
                </span>

                <div className="section-row-body">
                  <strong>{doc.title}</strong>
                  <span>
                    {doc.id} · {doc.kind} · {doc.cnr} · {doc.pages} page
                    {doc.pages === 1 ? "" : "s"}
                  </span>
                </div>

                <div className="section-row-meta">
                  <time>{formatDay(doc.received)}</time>
                  <span
                    className={`section-pill ${pipelinePill[doc.pipeline] ?? ""}`}
                  >
                    {doc.pipeline}
                  </span>
                </div>

              </li>
            ))}
          </ul>

        </div>
      </RoleSectionView>
    );
  }

  /* =====================================================
     TASK QUEUE
     ===================================================== */

  if (activeSection === "tasks") {
    const priorityPill: Record<string, string> = {
      High: "warn",
      Normal: "info",
      Low: "",
    };

    return (
      <RoleSectionView
        session={session}
        portal="NYAYMITRA STAFF PORTAL"
        title="Task"
        titleAccent="queue."
        heroDescription="Work assigned to you by the administrator, ordered by what falls due first."
        workspaceTitle="Work through your tasks"
        workspaceSubtitle="Assigned and visible to the admin"
        onBack={() => setActiveSection(null)}
      >
        <div className="section-stats">

          <div className="section-stat">
            <span>OPEN</span>
            <strong>{openTasks.length}</strong>
            <small>Awaiting action</small>
          </div>

          <div className="section-stat">
            <span>HIGH PRIORITY</span>
            <strong>
              {
                openTasks.filter((task) => task.priority === "High")
                  .length
              }
            </strong>
            <small>Among the open ones</small>
          </div>

          <div className="section-stat">
            <span>COMPLETED</span>
            <strong>
              {STAFF_TASKS.filter((task) => task.status === "Done").length}
            </strong>
            <small>Closed off</small>
          </div>

        </div>

        <div className="section-card">

          <span className="role-dashboard-section-label">
            ASSIGNED TO YOU
          </span>

          <h3>Task queue</h3>

          <p>
            Ordered by due date so the thing that falls due first is never
            buried under the thing that was asked for most recently.
          </p>

          <ul className="section-rows">
            {[...STAFF_TASKS]
              .sort((a, b) => a.due.localeCompare(b.due))
              .map((task) => {
                const days = daysFromToday(task.due);
                const overdue =
                  task.status !== "Done" &&
                  days !== null &&
                  days < 0;

                return (
                  <li key={task.id} className="section-row">

                    <span className="section-row-avatar" aria-hidden="true">
                      {task.status === "Done" ? (
                      <Check size={14} aria-hidden="true" />
                    ) : (
                      <Circle size={10} aria-hidden="true" />
                    )}
                    </span>

                    <div className="section-row-body">
                      <strong>{task.title}</strong>
                      <span>
                        {task.id} · {task.cnr}
                      </span>
                    </div>

                    <div className="section-row-meta">
                      <time>
                        {formatDay(task.due)}
                        {overdue ? " · overdue" : ""}
                      </time>
                      <span
                        className={`section-pill ${
                          priorityPill[task.priority] ?? ""
                        }`}
                      >
                        {task.priority}
                      </span>
                      <span
                        className={`section-pill ${
                          task.status === "Done" ? "good" : ""
                        }`}
                      >
                        {task.status}
                      </span>
                    </div>

                  </li>
                );
              })}
          </ul>

        </div>
      </RoleSectionView>
    );
  }

  /* =====================================================
     OPERATIONAL REPORTS
     ===================================================== */

  if (activeSection === "reports") {
    const byStage = new Map<string, number>();

    for (const item of allCases) {
      byStage.set(
        item.current_case_stage,
        (byStage.get(item.current_case_stage) ?? 0) + 1,
      );
    }

    return (
      <RoleSectionView
        session={session}
        portal="NYAYMITRA STAFF PORTAL"
        title="Operational"
        titleAccent="reports."
        heroDescription="The daily summary you file with the administrator — every figure below is counted from work in progress."
        workspaceTitle="File the daily summary"
        workspaceSubtitle="Submitted to the administrator"
        onBack={() => setActiveSection(null)}
      >
        <div className="section-stats">

          <div className="section-stat">
            <span>CASES SEEN</span>
            <strong>{allCases.length}</strong>
            <small>In today's window</small>
          </div>

          <div className="section-stat">
            <span>HEARINGS DUE</span>
            <strong>{upcomingHearings.length}</strong>
            <small>Still to be held</small>
          </div>

          <div className="section-stat">
            <span>DOCUMENTS</span>
            <strong>{STAFF_DOCUMENTS.length}</strong>
            <small>Through the pipeline</small>
          </div>

          <div className="section-stat">
            <span>TASKS CLOSED</span>
            <strong>
              {STAFF_TASKS.filter((task) => task.status === "Done").length}
            </strong>
            <small>Of {STAFF_TASKS.length} assigned</small>
          </div>

        </div>

        <div className="section-card">

          <span className="role-dashboard-section-label">
            SUMMARY
          </span>

          <h3>Work by stage</h3>

          <p>
            Submitted reports are read by the administrator alongside every
            other staff member's, which is how the admin compares activity
            across accounts.
          </p>

          <div className="section-chip-list">
            {[...byStage.entries()].map(([stage, count]) => (
              <span key={stage} className="section-chip">
                {stage} · {count}
              </span>
            ))}
          </div>

          <div className="section-record-block">

            {reportSent ? (
              <div className="section-pill good">
                Summary filed with the administrator
              </div>
            ) : (
              <button
                type="button"
                className="section-retry"
                onClick={() => setReportSent(true)}
              >
                File today's summary
              </button>
            )}

            <p className="section-record-note section-sublabel-list">
              The acknowledgement is local until the reporting endpoint
              exists — nothing has left this machine.
            </p>

          </div>

        </div>
      </RoleSectionView>
    );
  }

  /* =====================================================
     LAWYER VERIFICATION
     ===================================================== */

  if (activeSection === "lawyers") {
    return (
      <RoleSectionView
        session={session}
        portal="NYAYMITRA STAFF PORTAL"
        title="Lawyer"
        titleAccent="verification."
        heroDescription="Confirm or reject advocate registrations. The decision is recorded against the record and shown on every screen that carries a status."
        workspaceTitle="Rule on registrations"
        workspaceSubtitle="Filed under admin authority"
        onBack={() => setActiveSection(null)}
      >
        <div className="section-stats">

          <div className="section-stat">
            <span>IN DIRECTORY</span>
            <strong>
              {lawyerStatus === "ready" ? lawyerList.length : "—"}
            </strong>
            <small>Resolved through the detail endpoint</small>
          </div>

          <div className="section-stat">
            <span>VERIFIED</span>
            <strong>
              {lawyerStatus === "ready"
                ? lawyerList.filter(
                    (l) =>
                      l.profile_status?.toLowerCase() === "verified",
                  ).length
                : "—"}
            </strong>
            <small>Confirmed on this page</small>
          </div>

          <div className="section-stat">
            <span>REJECTED</span>
            <strong>
              {lawyerStatus === "ready"
                ? lawyerList.filter(
                    (l) =>
                      l.profile_status?.toLowerCase() === "rejected",
                  ).length
                : "—"}
            </strong>
            <small>Papers returned</small>
          </div>

        </div>

        <div className="section-card">

          <span className="role-dashboard-section-label">
            REGISTRATIONS
          </span>

          <h3>Ruling on an advocate</h3>

          <p>
            Verification is the platform's decision, not the
            advocate's — nobody can mark their own account
            verified. What you set here is what Manage Lawyers,
            Lawyer Records and the directory all show.
          </p>

          {lawyerStatus === "pending" && (
            <div className="section-empty">
              <span>⏳</span>
              <p>Reading the directory…</p>
            </div>
          )}

          {lawyerStatus === "error" && (
            <div className="section-retry">
              <span><TriangleAlert size={18} aria-hidden="true" /></span>
              <p>
                The lawyer service did not answer. It needs to be
                running on port 8000.
              </p>
              <button
                type="button"
                onClick={() => loadLawyerRecords()}
              >
                Try again
              </button>
            </div>
          )}

          {lawyerStatus === "ready" && (
            <ul className="section-rows">
              {lawyerList.map((lawyer) => {
                const status = lawyer.profile_status || "Not recorded";

                return (
                  <li
                    key={lawyer.lawyer_id}
                    className="section-row"
                  >

                    <span className="section-row-avatar">
                      {initialsOf(lawyer.full_name)}
                    </span>

                    <div className="section-row-body">
                      <strong>{lawyer.full_name}</strong>
                      <span>
                        {lawyer.lawyer_id}
                        {lawyer.city ? ` · ${lawyer.city}` : ""}
                      </span>
                    </div>

                    <div className="section-row-actions">

                      <span
                        className={`section-pill ${
                          status.toLowerCase() === "verified"
                            ? "good"
                            : status.toLowerCase() === "rejected"
                              ? "warn"
                              : "info"
                        }`}
                      >
                        {status}
                      </span>

                      <button
                        type="button"
                        className="section-action"
                        onClick={() =>
                          decideVerification(
                            lawyer.lawyer_id,
                            "Verified",
                          )
                        }
                      >
                        Verify
                      </button>

                      <button
                        type="button"
                        className="section-action is-danger"
                        onClick={() =>
                          decideVerification(
                            lawyer.lawyer_id,
                            "Rejected",
                          )
                        }
                      >
                        Reject
                      </button>

                    </div>

                  </li>
                );
              })}
            </ul>
          )}

          <p className="section-record-note section-sublabel-list">
            Held in the local verification store until a
            registration endpoint exists — the ruling is real
            inside the platform, and it survives a reload.
          </p>

        </div>
      </RoleSectionView>
    );
  }

  /* =====================================================
     RENDER
     ===================================================== */

  return (
    <div className="staff-dashboard">

      <RoleDashboardShell
        session={session}

        eyebrow="NYAYMITRA STAFF PORTAL"

        heroTitle="Operations"
        heroTitleAccent="under admin."

        heroDescription={
          "Authorized operational and case-management work " +
          "carried out under the administrator — everything " +
          "you do is accountable to the admin role."
        }

        workspaceLabel="STAFF WORKSPACE"
        workspaceTitle={`Welcome, ${session.fullName}`}
        workspaceSubtitle={
          "You are signed in with staff access, issued and " +
          "authorized by the administrator."
        }

        stats={stats}
        statsLabel="WORKLOAD OVERVIEW"
        statsHeading="Your operations snapshot"
        statsNote="Populates once staff APIs connect"

        sectionsLabel="OPERATIONS"
        sectionsHeading="Your assigned work"
        sections={sections}

        onSignOut={onSignOut}
      />

      {/* =================================================
          WORK ASSIGNMENT

          What the administrator said this account is for.
          Read straight off Staff Management, so the two
          screens cannot drift apart.
          ================================================= */}

      <div className="staff-dashboard-note staff-dashboard-assignment">

        <span><FolderOpen size={18} aria-hidden="true" /></span>

        <div>

          <strong>
            {myWork
              ? `Your assignment: ${myWork.label}`
              : "No work assigned yet"}
          </strong>

          <p>
            {myWork
              ? myWork.description
              : "The administrator sets this under Staff " +
                "Management. Until then only your granted " +
                "authorities apply."}
          </p>

        </div>

        <em>{myWork ? "ASSIGNED" : "UNASSIGNED"}</em>

      </div>

      {/* =================================================
          ADMIN-ACCOUNTABLE NOTE
          ================================================= */}

      <div className="staff-dashboard-note">

        <span><ShieldCheck size={18} aria-hidden="true" /></span>

        <div>

          <strong>Staff works under Admin authority</strong>

          <p>
            Staff accounts are issued by the administrator
            and every operation performed here is visible to
            and accountable to the admin role.
          </p>

        </div>

      </div>

      {/* =================================================
          AUTHORITIES THIS ACCOUNT HOLDS

          Mirrors the Access & Roles screen, so the person
          on the receiving end can see the decision rather
          than only discovering it when a button is missing.
          ================================================= */}

      <div className="staff-dashboard-authorities">

        <div className="staff-dashboard-authorities-head">

          <span><Lock size={18} aria-hidden="true" /></span>

          <div>

            <strong>Your authorities</strong>

            <p>
              Delegated by the administrator. Ask the admin
              under Access & Roles to change what you can do.
            </p>

          </div>

          <em>
            {granted.length} of {AUTHORITY_CATALOG.length} granted
          </em>

        </div>

        {/* Grouped the same way Access & Roles groups them, so a
            person recognises a category across both screens
            rather than re-learning the list. */}

        <div className="staff-dashboard-authority-groups">

          {authoritiesByCategory().map((group) => (
            <section
              key={group.category}
              className="staff-dashboard-authority-group"
            >

              <span className="role-dashboard-section-label">
                {group.category}
              </span>

              <ul>

                {group.authorities.map((authority) => {

                  const on = granted.includes(authority.id);

                  return (
                    <li
                      key={authority.id}
                      className={on ? "is-on" : "is-off"}
                    >

                      <span
                        className="staff-dashboard-authority-dot"
                        aria-hidden="true"
                      />

                      <div>
                        <strong>{authority.label}</strong>
                        <small>{authority.description}</small>
                      </div>

                      <em>{on ? "Granted" : "Not granted"}</em>

                    </li>
                  );
                })}

              </ul>

            </section>
          ))}

        </div>

      </div>

    </div>
  );
}

export default StaffDashboardPage;
