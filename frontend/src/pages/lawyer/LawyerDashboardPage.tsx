import { useEffect, useState } from "react";
import { IS_MOCK_AUTH } from "../../api/authApi";
import {
  Scale,
  MessageSquare,
  Mail,
  Check,
  GraduationCap,
  MapPin,
  type LucideIcon,
} from "lucide-react";
import type { Page } from "../../App";
import type { VerificationStatus } from "../../auth/session";
import {
  getLawyerById,
  getOwnLawyerProfile,
  type Lawyer,
} from "../../api/lawyerApi";
import "./LawyerDashboardPage.css";

const DEFAULT_LAWYER_ID =
  import.meta.env.VITE_LAWYER_ID || "LAWYER_0003";

type LawyerDashboardPageProps = {
  onNavigate: (page: Page) => void;
  lawyerId?: string;
  /* PENDING / APPROVED / REJECTED from the login session —
     the account's own verification state, echoed from the
     server. Undefined for sessions created before the field
     existed (treated as "nothing to warn about"). */
  verificationStatus?: VerificationStatus;
};

function LawyerDashboardPage({
  onNavigate,
  lawyerId,
  verificationStatus,
}: LawyerDashboardPageProps) {
  const effectiveLawyerId =
    lawyerId?.trim() || DEFAULT_LAWYER_ID;

  const [lawyer, setLawyer] =
    useState<Lawyer | null>(null);

  const [loading, setLoading] =
    useState(true);

  const [error, setError] =
    useState("");

  /*
   * LOAD LAWYER
   *
   * The function is intentionally inside useEffect.
   * This avoids the loadLawyer/exhaustive-deps warning.
   */
  useEffect(() => {
    let cancelled = false;

    async function loadLawyer() {
      try {
        setLoading(true);
        setError("");
        const data = IS_MOCK_AUTH
  ? await getLawyerById(effectiveLawyerId)
  : await getOwnLawyerProfile();

        if (!cancelled) {
          setLawyer(data);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Unable to load lawyer information."
          );

          setLawyer(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadLawyer();

    return () => {
      cancelled = true;
    };
  }, [effectiveLawyerId]);

  /*
   * VERIFICATION STATUS NOTICE
   *
   * Shown in every state below (loading included) because it is a
   * statement about the account, not about the directory data —
   * a pending lawyer must see it even when the profile request
   * behind the dashboard fails.
   */
  const statusNotice =
    verificationStatus === "PENDING" ? (
      <div
        className="lawyer-status-notice lawyer-status-notice--pending"
        role="status"
      >
        <strong>
          Your lawyer registration is pending
          admin verification.
        </strong>
        <span>
          An admin must approve your licence before
          verified-lawyer features — like receiving chats
          from users — unlock.
        </span>
      </div>
    ) : verificationStatus === "REJECTED" ? (
      <div
        className="lawyer-status-notice lawyer-status-notice--rejected"
        role="alert"
      >
        <strong>
          Your lawyer registration has been rejected.
        </strong>
        <span>
          Contact the administrator for details. You can
          still sign in to view your profile.
        </span>
      </div>
    ) : verificationStatus === "APPROVED" ? (
      <div
        className="lawyer-status-notice lawyer-status-notice--approved"
        role="status"
      >
        <strong>Verified advocate.</strong>
        <span>
          Your licence is approved — users can start chats
          with you.
        </span>
      </div>
    ) : null;

  /*
   * LOADING
   */
  if (loading) {
    return (
      <div className="lawyer-dashboard-loading">
        {statusNotice}

        <div className="lawyer-dashboard-spinner" />

        <p>
          Loading lawyer dashboard...
        </p>

        <span>
          Fetching professional information
          from NyayMitra.
        </span>
      </div>
    );
  }

  /*
   * ERROR
   */
  if (error || !lawyer) {
    return (
      <div className="lawyer-dashboard-page">

        {statusNotice}

        <div className="lawyer-dashboard-error">

          <div className="lawyer-dashboard-error-icon">
            !
          </div>

          <span className="lawyer-dashboard-section-label">
            LAWYER BACKEND
          </span>

          <h1>
            Unable to load your dashboard
          </h1>

          <p>
            {error ||
              "No lawyer information was returned by the API."}
          </p>

          <div className="lawyer-dashboard-error-meta">
            <span>Lawyer ID:</span>

            <strong>
              {effectiveLawyerId}
            </strong>
          </div>

          <button
            type="button"
            onClick={() =>
              window.location.reload()
            }
          >
            Retry
          </button>

        </div>

      </div>
    );
  }

  /*
   * REAL API DATA
   */

  const practiceAreas =
    lawyer.practice_areas ?? [];

  const courts =
    lawyer.courts_of_practice ?? [];

  const languages =
    lawyer.languages_known ?? [];

  const education =
    lawyer.education_qualifications ?? [];

  /*
   * PROFILE COMPLETENESS
   */

  const profileFields = [
    lawyer.full_name,
    lawyer.gender,
    lawyer.date_of_birth,
    lawyer.enrollment_number,
    lawyer.registration_number,
    lawyer.bar_council,
    lawyer.years_of_experience,
    practiceAreas.length > 0,
    courts.length > 0,
    lawyer.city,
    lawyer.state,
    lawyer.office_address,
    lawyer.professional_email,
    languages.length > 0,
    lawyer.professional_bio,
    lawyer.working_office_hours,
  ];

  const completedFields =
    profileFields.filter(Boolean).length;

  const profileCompleteness =
    Math.round(
      (completedFields /
        profileFields.length) *
        100
    );

  return (
    <div className="lawyer-dashboard-page">

      {statusNotice}

      {/* =====================================================
          HERO
          ===================================================== */}

      <section className="lawyer-dashboard-hero">

        <div className="lawyer-dashboard-hero-glow" />

        <div className="lawyer-dashboard-hero-content">

          <div className="lawyer-dashboard-eyebrow">
            <Scale size={15} aria-hidden="true" />
            NYAYMITRA LAWYER PORTAL
          </div>

          <h1>
            Your legal practice,
            <br />
            <span>simplified.</span>
          </h1>

          <p>
            Manage your professional information
            and access your NyayMitra lawyer
            workspace from one place.
          </p>

          <div className="lawyer-dashboard-hero-meta">

            <span>
              <Scale size={13} aria-hidden="true" />
              {lawyer.lawyer_id}
            </span>

            {lawyer.city && (
              <span>
                ⌖ {lawyer.city}
              </span>
            )}

            {lawyer.years_of_experience !== null &&
              lawyer.years_of_experience !== undefined && (
                <span>
                  ◷ {lawyer.years_of_experience} years
                  experience
                </span>
              )}

          </div>

        </div>

      </section>


      {/* =====================================================
          MAIN
          ===================================================== */}

      <main className="lawyer-dashboard-main">

        {/* =================================================
            PROFILE WELCOME
            ================================================= */}

        <section className="lawyer-dashboard-welcome">

          <div className="lawyer-dashboard-profile">

            <div className="lawyer-dashboard-avatar">
              {getInitials(
                lawyer.full_name
              )}
            </div>

            <div>

              <span className="lawyer-dashboard-section-label">
                LAWYER WORKSPACE
              </span>

              <h2>
                {lawyer.full_name}
              </h2>

              <p>
                {practiceAreas.length > 0
                  ? practiceAreas.join(" • ")
                  : "Legal Professional"}
              </p>

            </div>

          </div>

          <div className="lawyer-dashboard-profile-status">

            <span>
              Profile Status
            </span>

            <strong>
              {lawyer.profile_status ||
                "Not available"}
            </strong>

          </div>

        </section>


        {/* =================================================
            WORK — ACTIVE CASES + MESSAGES

            The two things an advocate does between hearings:
            check the matters on their list, and reply to the
            people on them. They lead the page because they
            change daily; everything below is standing
            information about the profile.
            ================================================= */}

        <section className="lawyer-dashboard-specialization-grid">

          <button
            type="button"
            className="lawyer-dashboard-wide-card
                       lawyer-dashboard-action-card"
            onClick={() => onNavigate("lawyerCases")}
          >

            <div className="lawyer-dashboard-card-heading">

              <div className="lawyer-dashboard-stat-icon purple">
                <Scale size={22} aria-hidden="true" />
              </div>

              <h3>
                Active Cases
              </h3>

            </div>

            <p className="lawyer-dashboard-muted">
              Every matter assigned to you — parties, stage,
              documents on file, the next hearing and any
              orders passed, with a shortcut to message the
              client.
            </p>

            <span className="lawyer-dashboard-action-cta">
              Open my caseload →
            </span>

          </button>


          <button
            type="button"
            className="lawyer-dashboard-wide-card
                       lawyer-dashboard-action-card"
            onClick={() => onNavigate("chat")}
          >

            <div className="lawyer-dashboard-card-heading">

              <div className="lawyer-dashboard-stat-icon blue">
                <MessageSquare size={22} aria-hidden="true" />
              </div>

              <h3>
                Messages
              </h3>

            </div>

            <p className="lawyer-dashboard-muted">
              Three channels in one inbox — clients, court
              staff, and fellow advocates — so replies go to
              whoever is actually waiting.
            </p>

            <span className="lawyer-dashboard-action-cta">
              Open inbox →
            </span>

          </button>

        </section>


        {/* =================================================
            PROFILE COMPLETENESS
            ================================================= */}

        <section className="lawyer-dashboard-profile-progress">

          <div>

            <span className="lawyer-dashboard-section-label">
              PROFILE COMPLETENESS
            </span>

            <h2>
              Keep your professional
              profile complete
            </h2>

            <p>
              More complete information makes
              the lawyer profile more useful
              across NyayMitra.
            </p>

          </div>

          <div className="lawyer-dashboard-progress">

            <div className="lawyer-dashboard-progress-number">
              {profileCompleteness}%
            </div>

            <div className="lawyer-dashboard-progress-track">
              <div
                style={{
                  width: `${profileCompleteness}%`,
                }}
              />
            </div>

          </div>

        </section>


        {/* =================================================
            VIEW YOUR PROFILE

            The professional snapshot this screen used to
            print in full now lives behind one button. Every
            field it showed — experience, practice areas,
            courts, registration, contact — is on the profile
            page, where it can also be corrected, so repeating
            it here only gave a second place to fall out of
            date.
            ================================================= */}

        <section className="lawyer-dashboard-cta">

          <div>

            <span>
              PROFESSIONAL PROFILE
            </span>

            <h2>
              View your profile
            </h2>

            <p>
              Open the complete profile to read your
              professional, contact, education and practice
              information — and edit anything that has
              changed.
            </p>

          </div>


          <div className="lawyer-dashboard-cta-actions">

            <button
              type="button"
              onClick={() =>
                onNavigate("lawyerProfile")
              }
            >
              View and edit profile →
            </button>

            <button
              type="button"
              className="secondary"
              onClick={() =>
                window.scrollTo({
                  top: 0,
                  behavior: "smooth",
                })
              }
            >
              Back to top ↑
            </button>

          </div>

        </section>


        {/* =================================================
            INFORMATION
            ================================================= */}

        <section className="lawyer-dashboard-info-section">

          <div className="lawyer-dashboard-info-grid">

            <InfoCard
              title="Location"
              icon={MapPin}
              tone="blue"
              items={[
                ["City", lawyer.city],
                ["District", lawyer.district],
                ["State", lawyer.state],
                ["Pincode", lawyer.pincode],
              ]}
            />

            <InfoCard
              title="Professional Contact"
              icon={Mail}
              tone="green"
              items={[
                [
                  "Email",
                  lawyer.professional_email,
                ],
                [
                  "Phone",
                  lawyer.professional_phone_number,
                ],
                [
                  "Office",
                  lawyer.office_phone,
                ],
                [
                  "Preferred",
                  lawyer.preferred_contact_method,
                ],
              ]}
            />

            <InfoCard
              title="Registration"
              icon={Scale}
              tone="purple"
              items={[
                [
                  "Enrollment",
                  lawyer.enrollment_number,
                ],
                [
                  "Registration",
                  lawyer.registration_number,
                ],
                [
                  "Bar Council",
                  lawyer.bar_council,
                ],
                [
                  "Year",
                  lawyer.year_of_enrollment?.toString(),
                ],
              ]}
            />

          </div>

        </section>


        {/* =================================================
            PRACTICE + COURTS
            ================================================= */}

        <section className="lawyer-dashboard-specialization-grid">

          <div className="lawyer-dashboard-wide-card">

            <div className="lawyer-dashboard-card-heading">

              <div className="lawyer-dashboard-stat-icon purple">
                §
              </div>

              <h3>
                Practice Areas
              </h3>

            </div>

            {practiceAreas.length > 0 ? (

              <div className="lawyer-dashboard-chip-list">

                {practiceAreas.map(
                  (area) => (
                    <span key={area}>
                      {area}
                    </span>
                  )
                )}

              </div>

            ) : (

              <p className="lawyer-dashboard-muted">
                No practice areas are available
                in the API response.
              </p>

            )}

          </div>


          <div className="lawyer-dashboard-wide-card">

            <div className="lawyer-dashboard-card-heading">

              <div className="lawyer-dashboard-stat-icon orange">
                ⌖
              </div>

              <h3>
                Courts of Practice
              </h3>

            </div>

            {courts.length > 0 ? (

              <ul className="lawyer-dashboard-list">

                {courts.map(
                  (court) => (
                    <li key={court}>
                      <Check size={13} aria-hidden="true" />
                      {court}
                    </li>
                  )
                )}

              </ul>

            ) : (

              <p className="lawyer-dashboard-muted">
                No courts are available
                in the API response.
              </p>

            )}

          </div>

        </section>


        {/* =================================================
            EDUCATION + LANGUAGES
            ================================================= */}

        <section className="lawyer-dashboard-info-grid-bottom">

          <div className="lawyer-dashboard-small-card">

            <div className="lawyer-dashboard-small-icon">
              <GraduationCap size={20} aria-hidden="true" />
            </div>

            <span>
              EDUCATION
            </span>

            <h3>
              {education.length > 0
                ? education.join(" • ")
                : "Not available"}
            </h3>

          </div>


          <div className="lawyer-dashboard-small-card">

            <div className="lawyer-dashboard-small-icon">
              文
            </div>

            <span>
              LANGUAGES
            </span>

            <h3>
              {languages.length > 0
                ? languages.join(" • ")
                : "Not available"}
            </h3>

          </div>


          <div className="lawyer-dashboard-small-card">

            <div className="lawyer-dashboard-small-icon">
              ◷
            </div>

            <span>
              OFFICE HOURS
            </span>

            <h3>
              {lawyer.working_office_hours ||
                "Not available"}
            </h3>

          </div>

        </section>

      </main>

    </div>
  );
}


/* =========================================================
   HELPERS
   ========================================================= */

function getInitials(
  name: string
): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map(
      (part) =>
        part[0]?.toUpperCase() || ""
    )
    .join("");
}


function InfoCard({
  title,
  icon: Icon,
  tone,
  items,
}: {
  title: string;
  icon: LucideIcon;
  tone:
    | "purple"
    | "blue"
    | "orange"
    | "green";
  items: Array<
    [
      string,
      string | number | null | undefined
    ]
  >;
}) {
  return (
    <div className="lawyer-dashboard-info-card">

      <div
        className={`lawyer-dashboard-info-icon ${tone}`}
      >
        <Icon size={20} aria-hidden="true" />
      </div>

      <div>

        <div className="lawyer-dashboard-info-title">
          <h3>
            {title}
          </h3>
        </div>

        <div className="lawyer-dashboard-detail-list">

          {items.map(
            ([label, value]) => (
              <div key={label}>

                <span>
                  {label}
                </span>

                <strong>
                  {value ||
                    "Not available"}
                </strong>

              </div>
            )
          )}

        </div>

      </div>

    </div>
  );
}


export default LawyerDashboardPage;
