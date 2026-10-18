import type { Session } from "../auth/session";
import type { LucideIcon } from "lucide-react";
import { Scale, User } from "lucide-react";
import { useT } from "../i18n/context";
import LanguageToggle from "../i18n/LanguageToggle";

/* =========================================================
   ROLE DASHBOARD SHELL

   Shared structure for the ADMIN and STAFF dashboards
   (the two roles whose screens are still being built out).

   The shell provides:
   - role hero with the signed-in identity
   - welcome bar with role badge + sign out
   - stat cards
   - section cards (the dashboard's actual screens)

   Both dashboards pass their own content config, so the
   admin and staff screens stay visually identical to the
   user and lawyer dashboards.
   ========================================================= */

export interface DashboardSection {
  id: string;
  icon: LucideIcon;
  title: string;
  description: string;
  status: "ready" | "planned";
  badge?: string;

  /* Overrides the CTA line. Needed because a section can be not-ready for
     two very different reasons — it is still being built, or the admin has
     withdrawn the authority — and "Under development" reads wrong for the
     second one. */
  cta?: string;
  onOpen?: () => void;
}

export interface DashboardStat {
  icon: LucideIcon;
  tone: "purple" | "blue" | "orange" | "green";
  label: string;
  value: string;
  detail: string;
}

type RoleDashboardShellProps = {
  session: Session;

  eyebrow: string;
  heroTitle: string;
  heroTitleAccent: string;
  heroDescription: string;

  workspaceLabel: string;
  workspaceTitle: string;
  workspaceSubtitle: string;

  stats: DashboardStat[];
  statsLabel: string;
  statsHeading: string;
  statsNote: string;

  sectionsLabel: string;
  sectionsHeading: string;
  sections: DashboardSection[];

  onSignOut: () => void;
};

function getInitials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || "")
    .join("");
}

function RoleDashboardShell({
  session,
  eyebrow,
  heroTitle,
  heroTitleAccent,
  heroDescription,
  workspaceLabel,
  workspaceTitle,
  workspaceSubtitle,
  stats,
  statsLabel,
  statsHeading,
  statsNote,
  sectionsLabel,
  sectionsHeading,
  sections,
  onSignOut,
}: RoleDashboardShellProps) {
  const { t } = useT();

  const roleLabel =
    session.role === "ADMIN"
      ? t("app.role.admin")
      : session.role === "STAFF"
        ? t("app.role.staff")
        : session.role;

  return (
    <div className="role-dashboard-page">

      {/* =================================================
          HERO
          ================================================= */}

      <section className="role-dashboard-hero">

        <div className="role-dashboard-hero-glow" />

        <div className="role-dashboard-hero-content">

          <div className="role-dashboard-eyebrow">
            <Scale size={15} aria-hidden="true" />
            {eyebrow}
          </div>

          <h1>
            {heroTitle}
            <br />
            <span>{heroTitleAccent}</span>
          </h1>

          <p>{heroDescription}</p>

          <div className="role-dashboard-hero-meta">

            <span>
              <Scale size={13} aria-hidden="true" />
              {roleLabel}
            </span>

            <span>
              <User size={13} aria-hidden="true" />
              {session.fullName}
            </span>

            <span>
              ⌁ {session.userId}
            </span>

          </div>

        </div>

      </section>


      {/* =================================================
          MAIN
          ================================================= */}

      <main className="role-dashboard-main">

        {/* =============================================
            WELCOME + SIGN OUT
            ============================================= */}

        <section className="role-dashboard-welcome">

          <div className="role-dashboard-profile">

            <div className="role-dashboard-avatar">
              {getInitials(session.fullName)}
            </div>

            <div>

              <span className="role-dashboard-section-label">
                {workspaceLabel}
              </span>

              <h2>{workspaceTitle}</h2>

              <p>{workspaceSubtitle}</p>

            </div>

          </div>

          <div className="role-dashboard-actions">

            <LanguageToggle />

            <button
              type="button"
              className="role-dashboard-signout"
              onClick={onSignOut}
            >
              {t("app.signOut")}
            </button>

          </div>

        </section>


        {/* =============================================
            STATS
            ============================================= */}

        <section className="role-dashboard-overview">

          <div className="role-dashboard-heading">

            <div>

              <span className="role-dashboard-section-label">
                {statsLabel}
              </span>

              <h2>{statsHeading}</h2>

            </div>

            <p>{statsNote}</p>

          </div>

          <div className="role-dashboard-stat-grid">

            {stats.map((stat) => (
              <div
                key={stat.label}
                className="role-dashboard-stat-card"
              >

                <div
                  className={`role-dashboard-stat-icon ${stat.tone}`}
                >
                  <stat.icon size={20} aria-hidden="true" />
                </div>

                <div>

                  <span>{stat.label}</span>

                  <strong>{stat.value}</strong>

                  <small>{stat.detail}</small>

                </div>

              </div>
            ))}

          </div>

        </section>


        {/* =============================================
            SECTIONS
            ============================================= */}

        <section className="role-dashboard-sections">

          <div className="role-dashboard-heading">

            <div>

              <span className="role-dashboard-section-label">
                {sectionsLabel}
              </span>

              <h2>{sectionsHeading}</h2>

            </div>

          </div>

          <div className="role-dashboard-section-grid">

            {sections.map((section) => {

              const isReady =
                section.status === "ready";

              const card = (
                <div
                  key={section.id}
                  className={`role-dashboard-section-card${isReady ? " is-ready" : ""}`}
                >

                  <div className="role-dashboard-section-top">

                    <div className="role-dashboard-section-icon">
                      <section.icon size={22} aria-hidden="true" />
                    </div>

                    <span
                      className={
                        isReady
                          ? "role-dashboard-section-badge ready"
                          : "role-dashboard-section-badge"
                      }
                    >
                      {section.badge ||
                        (isReady
                          ? t("roleDashboard.badge.open")
                          : t("roleDashboard.badge.soon"))}
                    </span>

                  </div>

                  <h3>{section.title}</h3>

                  <p>{section.description}</p>

                  <div className="role-dashboard-section-cta">
                    {isReady
                      ? t("roleDashboard.cta.open")
                      : section.cta ||
                        t("roleDashboard.cta.underDevelopment")}
                  </div>

                </div>
              );

              return section.onOpen && isReady ? (
                <button
                  key={section.id}
                  type="button"
                  className="role-dashboard-section-button"
                  onClick={section.onOpen}
                >
                  {card}
                </button>
              ) : (
                card
              );

            })}

          </div>

        </section>

      </main>

    </div>
  );
}

export default RoleDashboardShell;
