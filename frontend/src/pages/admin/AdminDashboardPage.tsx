import { useEffect, useRef, useState } from "react";
import {
  Users,
  Scale,
  FileText,
  Database,
  TriangleAlert,
} from "lucide-react";
import type { Session } from "../../auth/session";
import type { Page } from "../../App";
import RoleDashboardShell, {
  type DashboardSection,
  type DashboardStat,
} from "../../components/RoleDashboardShell";
import RoleSectionView from "../../components/RoleSectionView";
import { initialsOf } from "../../lib/initials";
import { DEMO_ACCOUNTS } from "../../api/authApi";
import { isDeactivated, toggleAccountStatus } from "../../api/accountApi";
import { getLawyerById } from "../../api/lawyerApi";
import type { Lawyer, VerificationState } from "../../api/lawyerApi";
import {
  fetchVerificationDocument,
  getAdminLawyers,
  setAdminVerification,
  toLabel,
  toStatus,
} from "../../api/adminApi";
import type { AdminDocument, AdminLawyer } from "../../api/adminApi";
import { getCases } from "../../api/caseApi";
import "../../components/RoleDashboardShell.css";
import "../../components/RoleSectionView.css";
import "./AdminDashboardPage.css";

/* =========================================================
   ADMIN DASHBOARD

   Platform-level administration:
   - managing users / lawyers / staff
   - lawyer records
   - platform data and access

   STAFF MANAGEMENT is implemented (staff accounts are
   issued by the admin — staff login goes through the
   admin login). The remaining sections are planned
   screens and are marked as such.
   ========================================================= */

type AdminDashboardPageProps = {
  session: Session;
  onSignOut: () => void;
  onNavigate: (page: Page) => void;
};

/* =========================================================
   PAGE SIZE

   Small on purpose: the directory, the registration rows
   and the Platform Data card all read this first page, and
   Lawyer Records resolves the same page through the detail
   endpoint for the profile fields the registration list
   does not carry.
   ========================================================= */

const RECORD_PAGE_SIZE = 12;

const SENIOR_YEARS = 15;

/* =========================================================
   REGISTRATION -> ROW

   The admin registration response is already a full record;
   the rows here read it as a Lawyer (the type every card
   speaks) with the status in the dashboard's own words.
   Fields the list does not carry — city, state — stay
   absent, and the row guards for that.
   ========================================================= */

function fromAdminLawyer(registration: AdminLawyer): Lawyer {
  return {
    lawyer_id: registration.lawyer_id,
    full_name: registration.full_name,
    professional_email: registration.email,
    enrollment_number: registration.license_id || null,
    years_of_experience: registration.years_of_experience,
    practice_areas: registration.practice_areas,
    bar_council: registration.bar_council,
    professional_phone_number: registration.professional_phone_number,
    professional_bio: registration.professional_bio,
    profile_status: toLabel(registration.verification_status),
    created_at: registration.created_at,
  };
}

function AdminDashboardPage({
  session,
  onSignOut,
}: AdminDashboardPageProps) {
  /* =====================================================
     SECTION NAVIGATION
     ===================================================== */

  const [activeSection, setActiveSection] =
    useState<string | null>(null);

  /* =====================================================
     ACCOUNT STATUS

     Citizen sign-in state. Kept locally alongside the store
     so the pill and the button change together.
     ===================================================== */

  const [accountStates, setAccountStates] = useState<
    Record<string, boolean>
  >({});

  const flipAccount = (userId: string) => {
    const next = toggleAccountStatus(userId);

    setAccountStates((previous) => ({
      ...previous,
      [userId]: next === "deactivated",
    }));
  };

  /* =====================================================
     LAWYER DIRECTORY (the admin registration service,
     fetched on demand)

     Three screens read this — Manage Lawyers, Lawyer
     Records and the lawyer count on Platform Data — but
     opening the dashboard should not cost a request. The
     fetch runs the first time one of those sections is
     opened and then stays warm.

     The ref guard exists because StrictMode invokes the
     effect twice in development; without it each visit to
     these screens would issue two identical requests. On
     failure the guard is released so the retry button can
     ask again rather than leaving a permanent error.
     ===================================================== */

  const lawyersRequested = useRef(false);

  const [lawyerList, setLawyerList] = useState<Lawyer[]>([]);
  const [lawyerTotal, setLawyerTotal] = useState(0);

  /* Document metadata per registration — it rides along in
     the same list response and is what the "View document"
     action on each row reads. */
  const [documents, setDocuments] = useState<
    Record<string, AdminDocument | null>
  >({});

  /* "pending" covers both not-yet-started and in flight, so the effect
     never has to set state to say it has begun — only to report the
     outcome, which it does from the async callback. */
  const [lawyerStatus, setLawyerStatus] = useState<
    "pending" | "ready" | "error"
  >("pending");

  const lawyerSectionOpen =
    activeSection === "lawyers" ||
    activeSection === "records" ||
    activeSection === "data";

  useEffect(() => {
    if (!lawyerSectionOpen || lawyerStatus !== "pending") return;
    if (lawyersRequested.current) return;

    lawyersRequested.current = true;

    void (async () => {
      try {
        const response = await getAdminLawyers({
          page: 1,
          limit: RECORD_PAGE_SIZE,
        });

        setLawyerList(response.lawyers.map(fromAdminLawyer));
        setLawyerTotal(response.total_count);
        setDocuments(
          Object.fromEntries(
            response.lawyers.map((item) => [item.lawyer_id, item.document]),
          ),
        );
        setLawyerStatus("ready");
      } catch {
        lawyersRequested.current = false;
        setLawyerStatus("error");
      }
    })();
  }, [lawyerSectionOpen, lawyerStatus]);

  const retryLawyers = () => setLawyerStatus("pending");

  /* =====================================================
     FULL RECORDS

     The registration list carries status, ruling and the
     uploaded papers' metadata itself; bar details, practice
     areas and contact fields still live on
     GET /api/lawyers/{id}, so the Records screen resolves
     each row there once the list has arrived, in parallel,
     and falls back to the list row for any lawyer whose
     detail call fails rather than dropping the card.
     ===================================================== */

  const recordsRequested = useRef(false);

  const [recordDetails, setRecordDetails] = useState<Lawyer[]>([]);
  const [recordStatus, setRecordStatus] = useState<
    "pending" | "ready" | "error"
  >("pending");

  useEffect(() => {
    if (activeSection !== "records" && activeSection !== "lawyers") return;
    if (recordStatus !== "pending" || recordsRequested.current) return;

    /* Needs the summary first — otherwise there is no ID list to resolve. */
    if (lawyerStatus !== "ready" || lawyerList.length === 0) return;

    recordsRequested.current = true;

    void (async () => {
      try {
        const resolved = await Promise.all(
          lawyerList.map((lawyer) =>
            getLawyerById(lawyer.lawyer_id).catch(() => lawyer),
          ),
        );

        /* The registration list is the server's word on status —
           the detail response may still be wearing a browser-local
           verdict from an older screen — so the stored status is
           stamped back over each record after every resolve. */
        const storedStatus = new Map(
          lawyerList.map((item) => [item.lawyer_id, item.profile_status]),
        );

        setRecordDetails(
          resolved.map((record) => ({
            ...record,
            profile_status:
              storedStatus.get(record.lawyer_id) ?? record.profile_status,
          })),
        );
        setRecordStatus("ready");
      } catch {
        recordsRequested.current = false;
        setRecordStatus("error");
      }
    })();
  }, [activeSection, recordStatus, lawyerStatus, lawyerList]);

  const retryRecords = () => setRecordStatus("pending");

  /* =====================================================
     VERIFICATION (server-backed)

     Ruling calls PATCH /api/admin/lawyers/{id} — ADMIN-only
     on the server — and the row repaints from the answer
     the server returns. A failure keeps the old status
     standing and puts the reason on screen; nothing is
     written to localStorage, because a status the database
     does not hold is not a status.
     ===================================================== */

  const [ruling, setRuling] = useState<{
    id: string;
    action: VerificationState;
  } | null>(null);
  const [rulingError, setRulingError] = useState<string | null>(null);

  const decideVerification = async (
    lawyerId: string,
    state: VerificationState,
  ): Promise<void> => {
    if (ruling) return;

    setRuling({ id: lawyerId, action: state });
    setRulingError(null);

    try {
      const updated = await setAdminVerification(lawyerId, toStatus(state));
      const stored = toLabel(updated.verification_status);

      setLawyerList((previous) =>
        previous.map((item) =>
          item.lawyer_id === lawyerId
            ? { ...item, profile_status: stored }
            : item,
        ),
      );

      setRecordDetails((previous) =>
        previous.map((item) =>
          item.lawyer_id === lawyerId
            ? { ...item, profile_status: stored }
            : item,
        ),
      );
    } catch (err) {
      setRulingError(
        err instanceof Error
          ? err.message
          : "The ruling could not be saved.",
      );
    } finally {
      setRuling(null);
    }
  };

  const verificationOf = (lawyerId: string): string => {
    /* The registration list carries the stored status itself —
       read it first, so a row never shows a verdict some other
       call happened to layer on. */
    const row = lawyerList.find((item) => item.lawyer_id === lawyerId);
    if (row?.profile_status) return row.profile_status;

    const detail = recordDetails.find(
      (item) => item.lawyer_id === lawyerId,
    );
    if (detail?.profile_status) return detail.profile_status;

    if (lawyerStatus === "ready") return "Not recorded";
    if (lawyerStatus === "error") return "Status unavailable";

    return "Checking…";
  };

  /* =====================================================
     VERIFICATION DOCUMENT

     The uploaded licence rides in the list response as
     metadata; the bytes come from the ADMIN-only endpoint
     and are shown from an object URL that is revoked
     shortly after — the file never becomes a routable
     address on our origin.
     ===================================================== */

  const [openingDocument, setOpeningDocument] =
    useState<string | null>(null);
  const [documentError, setDocumentError] = useState<string | null>(null);

  const documentFor = (lawyerId: string): AdminDocument | null =>
    documents[lawyerId] ?? null;

  const openDocument = async (lawyerId: string): Promise<void> => {
    if (openingDocument) return;

    setOpeningDocument(lawyerId);
    setDocumentError(null);

    try {
      const blob = await fetchVerificationDocument(lawyerId);
      const url = URL.createObjectURL(blob);

      window.open(url, "_blank", "noopener,noreferrer");

      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (err) {
      setDocumentError(
        err instanceof Error
          ? err.message
          : "The document could not be fetched.",
      );
    } finally {
      setOpeningDocument(null);
    }
  };

  /* One shared notice so Manage Lawyers, Lawyer Records and Platform Data
     cannot disagree about what "the directory is unavailable" looks like. */
  const lawyerNotice =
    lawyerStatus === "pending" ? (
      <div className="section-empty">
        <span aria-hidden="true">⏳</span>
        <p>Loading the lawyer directory…</p>
      </div>
    ) : lawyerStatus === "error" ? (
      <div className="section-empty">
        <span aria-hidden="true"><TriangleAlert size={18} /></span>
        <p>
          Could not reach the lawyer service. Start it on port 8000 and try
          again.
        </p>
        <button
          type="button"
          className="section-retry"
          onClick={retryLawyers}
        >
          Try again
        </button>
      </div>
    ) : lawyerList.length === 0 ? (
      <div className="section-empty">
        <span aria-hidden="true"><Scale size={18} /></span>
        <p>The directory has no lawyer records yet.</p>
      </div>
    ) : null;

  /* Records resolves a second endpoint on top of the summary, so it
     defers to lawyerNotice whenever the summary itself is the thing
     that has not arrived yet — otherwise both would describe the same
     wait differently. */
  const recordNotice =
    lawyerStatus !== "ready" ? (
      lawyerNotice
    ) : recordStatus === "error" ? (
      <div className="section-empty">
        <span aria-hidden="true"><TriangleAlert size={18} /></span>
        <p>The detail endpoint did not answer. Try again.</p>
        <button
          type="button"
          className="section-retry"
          onClick={retryRecords}
        >
          Try again
        </button>
      </div>
    ) : recordStatus === "pending" ? (
      <div className="section-empty">
        <span aria-hidden="true">⏳</span>
        <p>Resolving full records from the detail endpoint…</p>
      </div>
    ) : null;

  /* Every matter on the platform, seeded and newly filed.
     Read once per render rather than at each use site: the
     store touches localStorage, and the stats below are all
     derived from the same snapshot. */
  const allCases = getCases();

  /* =====================================================
     ISSUE STAFF ACCOUNT

     Staff login goes through the admin login: the admin
     issues the credentials, then the staff member signs
     in through the admin door on the login page.
     ===================================================== */

  /* =====================================================
     CONFIG
     ===================================================== */

  const stats: DashboardStat[] = [
    {
      icon: Users,
      tone: "purple",
      label: "USERS",
      value: "—",
      detail: "Citizen accounts",
    },
    {
      icon: Scale,
      tone: "blue",
      label: "LAWYERS",
      value: "—",
      detail: "Verified professionals",
    },
  ];

  const sections: DashboardSection[] = [
    {
      id: "users",
      icon: Users,
      title: "Manage Users",
      description:
        "View, verify and deactivate citizen accounts, and " +
        "review each user's case activity.",
      status: "ready",
      badge: "Open",
      onOpen: () => setActiveSection("users"),
    },
    {
      id: "lawyers",
      icon: Scale,
      title: "Manage Lawyers",
      description:
        "Verify or reject advocate registrations, and review " +
        "verification status against each lawyer record.",
      status: "ready",
      badge: "Open",
      onOpen: () => setActiveSection("lawyers"),
    },
    {
      id: "records",
      icon: FileText,
      title: "Lawyer Records",
      description:
        "Full lawyer records: enrollment details, practice " +
        "areas, courts, location and contact information.",
      status: "ready",
      badge: "Open",
      onOpen: () => setActiveSection("records"),
    },
    {
      id: "data",
      icon: Database,
      title: "Platform Data",
      description:
        "Platform-level data: cases, court orders, " +
        "translations and usage statistics.",
      status: "ready",
      badge: "Open",
      onOpen: () => setActiveSection("data"),
    },
  ];

  /* =====================================================
     MANAGE USERS
     ===================================================== */

  if (activeSection === "users") {
    /*
     * Accounts first, then any case owner the database knows
     * about that has no login issued. The admin needs both in
     * one list: only one of them can actually sign in, and
     * that difference is the whole point of this screen.
     */
    const rows = new Map<
      string,
      {
        id: string;
        name: string;
        email: string;
        issued: boolean;
        cases: number;
      }
    >();

    for (const account of DEMO_ACCOUNTS) {
      if (account.role !== "USER") continue;

      rows.set(account.userId, {
        id: account.userId,
        name: account.fullName,
        email: account.email,
        issued: true,
        cases: 0,
      });
    }

    for (const item of allCases) {
      const existing = rows.get(item.owner_user_id);

      if (existing) {
        existing.cases += 1;
        continue;
      }

      rows.set(item.owner_user_id, {
        id: item.owner_user_id,
        name: item.petitioner_name,
        email: "No login issued",
        issued: false,
        cases: 1,
      });
    }

    const citizens = [...rows.values()];

    return (
      <RoleSectionView
        session={session}
        portal="NYAYMITRA ADMIN PORTAL"
        title="Manage"
        titleAccent="users."
        heroDescription="Citizen accounts, their sign-in state and the case activity attached to each one."
        workspaceTitle="Review citizen accounts"
        workspaceSubtitle="Verify or deactivate from here"
        onBack={() => setActiveSection(null)}
      >
        <div className="section-stats">

          <div className="section-stat">
            <span>CITIZEN RECORDS</span>
            <strong>{citizens.length}</strong>
            <small>Known to the platform</small>
          </div>

          <div className="section-stat">
            <span>LOGIN ACCOUNTS</span>
            <strong>{citizens.filter((row) => row.issued).length}</strong>
            <small>Can sign in</small>
          </div>

          <div className="section-stat">
            <span>CASES ON FILE</span>
            <strong>{allCases.length}</strong>
            <small>Linked to citizens</small>
          </div>

        </div>

        <div className="section-card">

          <span className="role-dashboard-section-label">
            CITIZEN DIRECTORY
          </span>

          <h3>Accounts and case activity</h3>

          <p>
            A record can exist without a login — that happens when a case
            is filed on someone's behalf before their account is set up.
            Those are flagged so nothing gets worked on under the wrong
            name.
          </p>

          <ul className="section-rows">
            {citizens.map((row) => {
              /* Whether the administrator has switched this one off.
                 Only applies to accounts that can actually sign in —
                 a case owner with no login has nothing to switch. */
              const off = row.issued
                ? accountStates[row.id] ?? isDeactivated(row.id)
                : false;

              return (
                <li key={row.id} className="section-row">

                  <span className="section-row-avatar">
                    {initialsOf(row.name)}
                  </span>

                  <div className="section-row-body">
                    <strong>{row.name}</strong>
                    <span>
                      {row.id} · {row.email}
                    </span>
                  </div>

                  <div className="section-row-meta">
                    <time>
                      {row.cases} case{row.cases === 1 ? "" : "s"}
                    </time>

                    {row.issued ? (
                      <>
                        <span
                          className={`section-pill ${off ? "warn" : "good"}`}
                        >
                          {off ? "Deactivated" : "Active"}
                        </span>

                        <button
                          type="button"
                          className="section-toggle"
                          onClick={() => flipAccount(row.id)}
                        >
                          {off ? "Reactivate" : "Deactivate"}
                        </button>
                      </>
                    ) : (
                      <span className="section-pill warn">
                        No login issued
                      </span>
                    )}
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
     MANAGE LAWYERS
     ===================================================== */

  if (activeSection === "lawyers") {
    return (
      <RoleSectionView
        session={session}
        portal="NYAYMITRA ADMIN PORTAL"
        title="Manage"
        titleAccent="lawyers."
        heroDescription="The advocate directory, read live from the admin verification service — and the place where each registration is verified, rejected or left pending."
        workspaceTitle="Review lawyer registrations"
        workspaceSubtitle="Verify or reject from the row"
        onBack={() => setActiveSection(null)}
      >
        <div className="section-stats">

          <div className="section-stat">
            <span>IN DIRECTORY</span>
            <strong>
              {lawyerStatus === "ready" ? lawyerTotal : "—"}
            </strong>
            <small>Records on the service</small>
          </div>

          <div className="section-stat">
            <span>LOADED HERE</span>
            <strong>
              {lawyerStatus === "ready" ? lawyerList.length : "—"}
            </strong>
            <small>First page of {lawyerTotal}</small>
          </div>

          <div className="section-stat">
            <span>SENIOR COUNSEL</span>
            <strong>
              {lawyerStatus === "ready"
                ? lawyerList.filter(
                    (l) => (l.years_of_experience ?? 0) >= SENIOR_YEARS,
                  ).length
                : "—"}
            </strong>
            <small>{SENIOR_YEARS}+ years on this page</small>
          </div>

          <div className="section-stat">
            <span>VERIFIED</span>
            <strong>
              {lawyerStatus === "ready"
                ? lawyerList.filter(
                    (l) => l.profile_status?.toLowerCase() === "verified",
                  ).length
                : "—"}
            </strong>
            <small>Papers confirmed on this page</small>
          </div>

          <div className="section-stat">
            <span>AWAITING REVIEW</span>
            <strong>
              {lawyerStatus === "ready"
                ? lawyerList.filter(
                    (l) => l.profile_status?.toLowerCase() === "pending",
                  ).length
                : "—"}
            </strong>
            <small>Registrations to rule on</small>
          </div>

        </div>

        <div className="section-card">

          <span className="role-dashboard-section-label">
            REGISTRATIONS
          </span>

          <h3>Lawyer registrations</h3>

          <p>
            Every row here is the registration record itself, read from
            the admin verification service: status, ruling and the
            uploaded papers' metadata all come from the server. Ruling
            here is the platform's decision, not the advocate's: it is
            written to the record and shown everywhere the status
            appears.
          </p>

          {lawyerNotice ?? (
            <>
              {rulingError && (
                <div className="section-empty" role="alert">
                  <span aria-hidden="true"><TriangleAlert size={18} /></span>
                  <p>{rulingError}</p>
                </div>
              )}

              {documentError && (
                <div className="section-empty" role="alert">
                  <span aria-hidden="true"><TriangleAlert size={18} /></span>
                  <p>{documentError}</p>
                </div>
              )}

              <ul className="section-rows">
                {lawyerList.map((lawyer) => {
                  const senior =
                    (lawyer.years_of_experience ?? 0) >= SENIOR_YEARS;
                  const status = verificationOf(lawyer.lawyer_id);
                  const documentMeta = documentFor(lawyer.lawyer_id);
                  const busyRuling = ruling?.id === lawyer.lawyer_id;
                  const busyOpening = openingDocument === lawyer.lawyer_id;

                  return (
                    <li key={lawyer.lawyer_id} className="section-row">

                      <span className="section-row-avatar">
                        {initialsOf(lawyer.full_name)}
                      </span>

                      <div className="section-row-body">
                        <strong>{lawyer.full_name}</strong>
                        <span>
                          {lawyer.lawyer_id}
                          {lawyer.city ? ` · ${lawyer.city}` : ""}
                          {lawyer.state ? `, ${lawyer.state}` : ""}
                          {lawyer.professional_email
                            ? ` · ${lawyer.professional_email}`
                            : ""}
                        </span>
                      </div>

                      <div className="section-row-meta">
                        <time>
                          {lawyer.years_of_experience ?? 0} yrs
                        </time>
                        <span
                          className={`section-pill ${senior ? "info" : ""}`}
                        >
                          {senior ? "Senior" : "Practising"}
                        </span>
                      </div>

                      {/* ----------------------------------------
                          VERIFICATION

                          The decision itself, on the row it
                          belongs to — written to the server
                          and repainted from its answer, with
                          the uploaded papers one click away.
                          ---------------------------------------- */}

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

                        {documentMeta ? (
                          <button
                            type="button"
                            className="section-action"
                            title={`${documentMeta.filename} · ${Math.max(
                              1,
                              Math.ceil(documentMeta.size_bytes / 1024),
                            )} KB`}
                            disabled={openingDocument !== null}
                            onClick={() =>
                              void openDocument(lawyer.lawyer_id)
                            }
                          >
                            {busyOpening ? "Opening…" : "View document"}
                          </button>
                        ) : (
                          <span className="section-pill">No document</span>
                        )}

                        <button
                          type="button"
                          className="section-action"
                          disabled={ruling !== null}
                          onClick={() =>
                            void decideVerification(
                              lawyer.lawyer_id,
                              "Verified",
                            )
                          }
                        >
                          {busyRuling && ruling?.action === "Verified"
                            ? "Saving…"
                            : "Verify"}
                        </button>

                        <button
                          type="button"
                          className="section-action is-danger"
                          disabled={ruling !== null}
                          onClick={() =>
                            void decideVerification(
                              lawyer.lawyer_id,
                              "Rejected",
                            )
                          }
                        >
                          {busyRuling && ruling?.action === "Rejected"
                            ? "Saving…"
                            : "Reject"}
                        </button>

                      </div>

                    </li>
                  );
                })}
              </ul>
            </>
          )}

        </div>
      </RoleSectionView>
    );
  }

  /* =====================================================
     LAWYER RECORDS — the full file, not the summary
     ===================================================== */

  if (activeSection === "records") {
    return (
      <RoleSectionView
        session={session}
        portal="NYAYMITRA ADMIN PORTAL"
        title="Lawyer"
        titleAccent="records."
        heroDescription="Enrollment details, practice areas, courts, location and contact information — the full profile behind each summary row."
        workspaceTitle="Read the complete records"
        workspaceSubtitle="Resolved through the detail endpoint"
        onBack={() => setActiveSection(null)}
      >
        <div className="section-card">

          <span className="role-dashboard-section-label">
            FULL RECORDS
          </span>

          <h3>Enrollment and practice</h3>

          <p>
            The same first page as Manage Lawyers, but resolved through
            the lawyer detail endpoint — that is the only way to see bar
            details, practice areas and contact fields, because the
            registration list leaves them blank. Verification status is
            stamped from the registration list, so both screens read the
            same stored ruling.
          </p>

          {recordNotice ?? (
            <div>
              {recordDetails.map((lawyer) => (
                <div
                  key={lawyer.lawyer_id}
                  className="section-record"
                >

                  <header className="section-record-head">

                    <span className="section-row-avatar">
                      {initialsOf(lawyer.full_name)}
                    </span>

                    <div>
                      <strong>{lawyer.full_name}</strong>
                      <span>
                        {lawyer.lawyer_id}
                        {lawyer.enrollment_number
                          ? ` · Enr. ${lawyer.enrollment_number}`
                          : ""}
                      </span>
                    </div>

                    <span
                      className={`section-pill ${
                        lawyer.profile_status?.toLowerCase() === "verified"
                          ? "good"
                          : lawyer.profile_status?.toLowerCase() ===
                              "rejected"
                            ? "warn"
                            : "info"
                      }`}
                    >
                      {lawyer.profile_status || "No status recorded"}
                    </span>

                  </header>

                  <dl className="section-field-grid">

                    <div>
                      <dt>Bar council</dt>
                      <dd>{lawyer.bar_council || "—"}</dd>
                    </div>

                    <div>
                      <dt>Year of enrolment</dt>
                      <dd>{lawyer.year_of_enrollment || "—"}</dd>
                    </div>

                    <div>
                      <dt>Experience</dt>
                      <dd>
                        {lawyer.years_of_experience ?? 0} years
                      </dd>
                    </div>

                    <div>
                      <dt>Location</dt>
                      <dd>
                        {lawyer.city || lawyer.district || "—"}
                        {lawyer.state ? `, ${lawyer.state}` : ""}
                      </dd>
                    </div>

                    <div>
                      <dt>Phone</dt>
                      <dd>
                        {lawyer.professional_phone_number ||
                          lawyer.office_phone ||
                          "—"}
                      </dd>
                    </div>

                    <div>
                      <dt>Email</dt>
                      <dd>
                        {lawyer.professional_email || "—"}
                      </dd>
                    </div>

                  </dl>

                  <div className="section-record-block">

                    <span className="role-dashboard-section-label">
                      PRACTICE AREAS
                    </span>

                    {lawyer.practice_areas?.length ? (
                      <div className="section-chip-list">
                        {lawyer.practice_areas.map((area) => (
                          <span key={area} className="section-chip">
                            {area}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <p className="section-record-note">Not listed.</p>
                    )}

                  </div>

                  <div className="section-record-block">

                    <span className="role-dashboard-section-label">
                      COURTS OF PRACTICE
                    </span>

                    {lawyer.courts_of_practice?.length ? (
                      <div className="section-chip-list">
                        {lawyer.courts_of_practice.map((court) => (
                          <span key={court} className="section-chip">
                            {court}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <p className="section-record-note">Not listed.</p>
                    )}

                  </div>

                </div>
              ))}
            </div>
          )}

        </div>
      </RoleSectionView>
    );
  }

  /* =====================================================
     PLATFORM DATA
     ===================================================== */

  if (activeSection === "data") {
    const byCourt = new Map<string, number>();
    const byStage = new Map<string, number>();

    for (const item of allCases) {
      byCourt.set(
        item.court_name,
        (byCourt.get(item.court_name) ?? 0) + 1,
      );
      byStage.set(
        item.current_case_stage,
        (byStage.get(item.current_case_stage) ?? 0) + 1,
      );
    }

    const ownerIds = new Set(allCases.map((item) => item.owner_user_id));

    return (
      <RoleSectionView
        session={session}
        portal="NYAYMITRA ADMIN PORTAL"
        title="Platform"
        titleAccent="data."
        heroDescription="Platform-level figures — cases, citizens and the lawyer directory — counted from the records the services actually hold."
        workspaceTitle="Read the platform figures"
        workspaceSubtitle="Counted live, not stored"
        onBack={() => setActiveSection(null)}
      >
        <div className="section-stats">

          <div className="section-stat">
            <span>CASES ON FILE</span>
            <strong>{allCases.length}</strong>
            <small>Across all courts</small>
          </div>

          <div className="section-stat">
            <span>CITIZENS ON CASES</span>
            <strong>{ownerIds.size}</strong>
            <small>Distinct owners</small>
          </div>

          <div className="section-stat">
            <span>HEARINGS BOOKED</span>
            <strong>
              {allCases.reduce(
                (sum, item) =>
                  sum + (item.calculated_metrics?.total_hearings_scheduled ?? 0),
                0,
              )}
            </strong>
            <small>Scheduled to date</small>
          </div>

          <div className="section-stat">
            <span>LAWYERS</span>
            <strong>
              {lawyerStatus === "ready" ? lawyerList.length : "—"}
            </strong>
            <small>From the directory</small>
          </div>

        </div>

        <div className="section-card">

          <span className="role-dashboard-section-label">
            BREAKDOWN
          </span>

          <h3>Cases by court</h3>

          <p>
            Useful for spotting where filings concentrate, which is the
            first thing anyone asks when case numbers move.
          </p>

          <div className="section-stats">
            {[...byCourt.entries()].map(([court, count]) => (
              <div key={court} className="section-stat">
                <span>COURT</span>
                <strong>{count}</strong>
                <small>{court}</small>
              </div>
            ))}
          </div>

          <span className="role-dashboard-section-label section-sublabel">
            CASES BY STAGE
          </span>

          <div className="section-chip-list section-sublabel-list">
            {[...byStage.entries()].map(([stage, count]) => (
              <span key={stage} className="section-chip">
                {stage} · {count}
              </span>
            ))}
          </div>

        </div>

        <div className="section-card">

          <span className="role-dashboard-section-label">
            DIRECTORY SERVICE
          </span>

          <h3>Lawyer directory</h3>

          <p>
            The only figure here that does not come from local records —
            it is read from the lawyer API, so it waits for the service.
          </p>

          {lawyerNotice ?? (
            <div className="section-chip-list">
              <span className="section-chip">
                {lawyerList.length} records returned
              </span>
            </div>
          )}

        </div>
      </RoleSectionView>
    );
  }

  /* =====================================================
     DEFAULT — ADMIN DASHBOARD
     ===================================================== */

  return (
    <RoleDashboardShell
      session={session}

      eyebrow="NYAYMITRA ADMIN PORTAL"

      heroTitle="Platform"
      heroTitleAccent="administration."

      heroDescription={
        "Manage users and lawyers, review records and " +
        "platform data — all from one console."
      }

      workspaceLabel="ADMIN WORKSPACE"
      workspaceTitle={`Welcome, ${session.fullName}`}
      workspaceSubtitle={
        "You are signed in with full platform " +
        "administrative access."
      }

      stats={stats}
      statsLabel="PLATFORM SNAPSHOT"
      statsHeading="Everything at a glance"
      statsNote="Counts update as backend APIs connect"

      sectionsLabel="ADMINISTRATION"
      sectionsHeading="Manage the platform"
      sections={sections}

      onSignOut={onSignOut}
    />
  );
}

export default AdminDashboardPage;
