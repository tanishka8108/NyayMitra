import type { ReactNode } from "react";
import { Scale } from "lucide-react";

import type { Session } from "../auth/session";
import { initialsOf } from "../lib/initials";

/* =========================================================
   ROLE SECTION VIEW

   The chrome every inline dashboard section wears: a hero
   naming the screen, then a welcome bar carrying the signed
   in identity and a back control, then the body.

   Admin already had this shape hand-written twice (Staff
   Management, Access & Roles). Rather than repeat it another
   nine times for the remaining admin and staff screens, it
   lives here once. The two existing screens still build it
   by hand and can be migrated when convenient — this
   component is additive, not a refactor.
   ========================================================= */

type RoleSectionViewProps = {
  session: Session;

  /** Portal eyebrow, e.g. "NYAYMITRA ADMIN PORTAL". */
  portal: string;

  /** Hero heading and its accent second line. */
  title: string;
  titleAccent: string;
  heroDescription: string;

  /** Welcome-bar heading, e.g. "Review citizen accounts". */
  workspaceTitle: string;
  workspaceSubtitle: string;

  onBack: () => void;
  backLabel?: string;

  children: ReactNode;
};

/**
 * Hero + welcome bar + back control, then whatever the caller wants to
 * show underneath. Row avatars use `initialsOf` from lib so they line up
 * with the ones this component draws for the signed-in identity.
 */
function RoleSectionView({
  session,
  portal,
  title,
  titleAccent,
  heroDescription,
  workspaceTitle,
  workspaceSubtitle,
  onBack,
  backLabel = "← Back to dashboard",
  children,
}: RoleSectionViewProps) {
  return (
    <div className="role-dashboard-page">

      <section className="role-dashboard-hero">

        <div className="role-dashboard-hero-glow" />

        <div className="role-dashboard-hero-content">

          <div className="role-dashboard-eyebrow">
            <Scale size={15} aria-hidden="true" />
            {portal}
          </div>

          <h1>
            {title}
            <br />
            <span>{titleAccent}</span>
          </h1>

          <p>{heroDescription}</p>

        </div>

      </section>

      <main className="role-dashboard-main">

        <section className="role-dashboard-welcome">

          <div className="role-dashboard-profile">

            <div className="role-dashboard-avatar">
              {initialsOf(session.fullName)}
            </div>

            <div>

              <span className="role-dashboard-section-label">
                SIGNED IN
              </span>

              <h2>{workspaceTitle}</h2>

              <p>
                {workspaceSubtitle} — {session.fullName} (
                {session.userId})
              </p>

            </div>

          </div>

          <button
            type="button"
            className="role-dashboard-signout"
            onClick={onBack}
          >
            {backLabel}
          </button>

        </section>

        {children}

      </main>

    </div>
  );
}

export default RoleSectionView;
