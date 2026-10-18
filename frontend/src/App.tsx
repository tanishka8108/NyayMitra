import { useCallback, useState } from "react";
import { LogOut } from "lucide-react";
import "./App.css";

import ThemeToggle from "./components/ThemeToggle";
import LanguageToggle from "./i18n/LanguageToggle";
import { useT } from "./i18n/context";

// ================= AUTH =================

import LoginPage from "./pages/auth/LoginPage";
import RegisterPage from "./pages/auth/RegisterPage";
import type { Session } from "./auth/session";
import {
  loadSession,
  saveSession,
  clearSession,
} from "./auth/session";

// ================= USER PAGES =================

import DashboardPage from "./pages/user/DashboardPage";
import CaseSearchPage from "./pages/user/CaseSearchPage";
import LawyerPage from "./pages/user/LawyerPage";
import CourtOrdersPage from "./pages/user/CourtOrdersPage";
import TranslationPage from "./pages/user/TranslationPage";
import DelayAnalysisPage from "./pages/user/DelayAnalysisPage";
import VoiceNyayMitraPage from "./pages/user/VoiceNyayMitraPage";
import JurisAIPage from "./pages/user/JurisAIPage";
import CaseTimelinePage from "./pages/user/CaseTimelinePage";

// ================= LAWYER PAGES =================

import LawyerDashboardPage from "./pages/lawyer/LawyerDashboardPage";
import LawyerProfilePage from "./pages/lawyer/LawyerProfilePage";
import LawyerCasesPage from "./pages/lawyer/LawyerCasesPage";

// ================= ADMIN PAGES =================

import AdminDashboardPage from "./pages/admin/AdminDashboardPage";

// ================= STAFF PAGES =================

import StaffDashboardPage from "./pages/staff/StaffDashboardPage";

// ================= SHARED PAGES =================

import ChatPage from "./pages/shared/ChatPage";
import type { ChatTarget } from "./api/chatApi";

/* =========================================================
   PAGE TYPES
   ========================================================= */

export type Page =
  // USER
  | "dashboard"
  | "cases"
  | "lawyer"
  | "viewLawyer"
  | "orders"
  | "translation"
  | "delay"
  | "voice"
  | "jurisAI"
  | "timeline"

  // LAWYER
  | "lawyerDashboard"
  | "lawyerProfile"
  | "lawyerCases"

  // ADMIN
  | "adminDashboard"

  // STAFF
  | "staffDashboard"

  // SHARED — every role reaches this one
  | "chat";

/* =========================================================
   DEVELOPMENT LAWYER ID

   Fallback used only when the signed-in session does not
   carry a lawyer ID (for example, an older saved session).
   After login, the LAWYER session's own lawyerId wins.
   ========================================================= */

const FALLBACK_LAWYER_ID =
  import.meta.env.VITE_LAWYER_ID?.trim() || "LAWYER_0003";

/* Initials for the session avatar — "Asha Verma" -> "AV". */
function initialsFromName(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);

  if (parts.length === 0) return "?";
  if (parts.length === 1) {
    return parts[0].slice(0, 2).toUpperCase();
  }

  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/* =========================================================
   HOME PAGE FOR EACH ROLE

   Login → role detection → respective dashboard.
   ========================================================= */

function homePageForRole(
  role: Session["role"],
): Page {
  switch (role) {
    case "USER":
      return "dashboard";

    case "LAWYER":
      return "lawyerDashboard";

    case "ADMIN":
      return "adminDashboard";

    case "STAFF":
      return "staffDashboard";

    default:
      return "dashboard";
  }
}

/* =========================================================
   WHICH PAGES BELONG TO WHICH ROLE

   Used as a guard so a role can never render another
   role's dashboard (defence in depth on top of the
   conditional rendering below).
   ========================================================= */

const PAGES_BY_ROLE: Record<
  Session["role"],
  Page[]
> = {
  USER: [
    "dashboard",
    "cases",
    "chat",
    "lawyer",
    "viewLawyer",
    "orders",
    "translation",
    "delay",
    "voice",
    "jurisAI",
    "timeline",
  ],

  LAWYER: ["lawyerDashboard", "lawyerProfile", "lawyerCases", "chat"],

  ADMIN: ["adminDashboard", "chat"],

  STAFF: ["staffDashboard", "chat"],
};

function pageOwnedByRole(
  role: Session["role"],
  page: Page,
): boolean {
  return PAGES_BY_ROLE[role].includes(page);
}

/* =========================================================
   APP
   ========================================================= */

function App() {

  const { t } = useT();

  /*
   * ONE LOGIN SYSTEM
   *
   * No session  → Login page (role selection).
   * Session     → the role on the session decides which
   *               dashboard opens.
   */

  const [session, setSession] =
    useState<Session | null>(() => loadSession());

  /*
   * Which screen to show while signed out: the door-picker login or
   * citizen registration. Registration is the only public form —
   * every dashboard behind it requires a server-validated session.
   */
  const [authView, setAuthView] =
    useState<"login" | "register">("login");

  /*
   * On a page refresh the session is restored from
   * storage, so the starting page must be derived from
   * the restored role — otherwise a lawyer refreshing
   * the browser would land on a user page and see a
   * blank screen.
   */

  const [activePage, setActivePage] =
    useState<Page>(() => {
      const existing = loadSession();

      return existing
        ? homePageForRole(existing.role)
        : "dashboard";
    });

  /*
   * Lawyer the signed-in citizen is currently reading.
   * Set when a card on the "Find a Lawyer" page is opened.
   */
  const [selectedLawyerId, setSelectedLawyerId] =
    useState<string | null>(null);

  /*
   * Thread ChatPage should open as soon as it mounts.
   * A "Chat with Lawyer" button sets this, then navigates;
   * ChatPage clears it via onTargetConsumed so returning to
   * the inbox normally does not re-open it.
   */
  const [chatTarget, setChatTarget] =
    useState<ChatTarget | null>(null);

  const clearChatTarget = useCallback(() => {
    setChatTarget(null);
  }, []);

  /* =======================================================
     LOGIN / LOGOUT
     ======================================================= */

  const handleAuthenticated = (next: Session) => {
    saveSession(next);

    setSession(next);
    setAuthView("login");
    setSelectedLawyerId(null);
    setActivePage(homePageForRole(next.role));

    window.scrollTo({ top: 0 });
  };

  const handleSignOut = () => {
    clearSession();

    setSession(null);
    setAuthView("login");
    setSelectedLawyerId(null);
    setActivePage("dashboard");

    window.scrollTo({ top: 0 });
  };

  /* =======================================================
     NOT SIGNED IN → LOGIN / REGISTER
     ======================================================= */

  if (!session) {
    return (
      <div className="app">
        {/* Theme control for every signed-out view (login door
            picker, role form, all registration steps). */}
        <div className="app-theme-corner">
          <LanguageToggle />
          <ThemeToggle />
        </div>
        {authView === "register" ? (
          <RegisterPage
            onAuthenticated={handleAuthenticated}
            onBack={() => setAuthView("login")}
          />
        ) : (
          <LoginPage
            onAuthenticated={handleAuthenticated}
            onRegister={() => setAuthView("register")}
          />
        )}
      </div>
    );
  }

  /* =======================================================
     SIGNED IN → ROLE ROUTING
     ======================================================= */


const goToPage = (page: Page) => {
  // Prevent navigation to pages not allowed for this role.
  if (!pageOwnedByRole(session.role, page)) {
    setChatTarget(null);
    setSelectedLawyerId(null);
    setActivePage(homePageForRole(session.role));

    window.scrollTo({
      top: 0,
      behavior: "smooth",
    });

    return;
  }

  // Clear any previous chat target when opening the inbox normally.
  if (page === "chat") {
    setChatTarget(null);
  }

  setActivePage(page);

  window.scrollTo({
    top: 0,
    behavior: "smooth",
  });
};


  const goBackToDashboard = () => {
    setActivePage(homePageForRole(session.role));

    window.scrollTo({
      top: 0,
      behavior: "smooth",
    });
  };

  /* Opens a lawyer's full profile from the results grid. */
  const openLawyerProfile = (lawyerId: string) => {
    setSelectedLawyerId(lawyerId);
    setActivePage("viewLawyer");

    window.scrollTo({
      top: 0,
      behavior: "smooth",
    });
  };

  /*
   * Opens the inbox straight onto one thread. Used by
   * "Chat with Lawyer" so the user never has to hunt for the
   * conversation they just asked for.
   */
  const startChat = (target: ChatTarget) => {
    setChatTarget(target);
    setActivePage("chat");

    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const lawyerId =
    session.lawyerId?.trim() || FALLBACK_LAWYER_ID;

  /*
   * GUARD
   *
   * If activePage somehow points at a page that does not
   * belong to the signed-in role (for example a stale
   * stored value), fall back to that role's dashboard
   * instead of rendering a blank screen.
   */

  const page = pageOwnedByRole(session.role, activePage)
    ? activePage
    : homePageForRole(session.role);

  return (
    <div className="app">

      {/* =================================================
          USER DASHBOARD
          ================================================= */}

      {session.role === "USER" &&
        page === "dashboard" && (
          <DashboardPage onNavigate={goToPage} />
        )}


      {/* =================================================
          USER FEATURE PAGES
          ================================================= */}

      {session.role === "USER" &&
        page === "cases" && (
          <CaseSearchPage
            userId={session.userId}
            onBack={goBackToDashboard}
            onChat={startChat}
            /* An order opened from a case dashboard goes to the
               Court Orders screen, where the existing extraction
               and explanation service lives. */
            onOpenCourtOrders={() => goToPage("orders")}
          />
        )}

      {session.role === "USER" &&
        (page === "lawyer" ||
          (page === "viewLawyer" &&
            !selectedLawyerId)) && (
          <LawyerPage
            onBack={goBackToDashboard}
            onViewProfile={openLawyerProfile}
            onChat={startChat}
          />
        )}

      {session.role === "USER" &&
        page === "viewLawyer" &&
        selectedLawyerId && (
          <LawyerProfilePage
            lawyerId={selectedLawyerId}
            onBack={() => goToPage("lawyer")}
          />
        )}

      {session.role === "USER" &&
        page === "orders" && (
          <CourtOrdersPage
            userId={session.userId}
            onBack={goBackToDashboard}
          />
        )}

      {session.role === "USER" &&
        page === "translation" && (
          <TranslationPage
            onBack={goBackToDashboard}
          />
        )}

      {session.role === "USER" &&
        page === "delay" && (
          <DelayAnalysisPage
            userId={session.userId}
            onBack={goBackToDashboard}
          />
        )}

      {session.role === "USER" &&
        page === "voice" && (
          <VoiceNyayMitraPage
            onBack={goBackToDashboard}
          />
        )}

      {session.role === "USER" &&
        page === "jurisAI" && (
          <JurisAIPage onBack={goBackToDashboard} />
        )}

      {session.role === "USER" &&
        page === "timeline" && (
          <CaseTimelinePage
            userId={session.userId}
            onBack={goBackToDashboard}
          />
        )}


      {/* =================================================
          LAWYER DASHBOARD
          ================================================= */}

      {session.role === "LAWYER" &&
        page === "lawyerDashboard" && (
          <LawyerDashboardPage
            onNavigate={goToPage}
            lawyerId={lawyerId}
            verificationStatus={session.verificationStatus}
          />
        )}


      {/* =================================================
          LAWYER PROFILE
          ================================================= */}

      {session.role === "LAWYER" &&
        page === "lawyerProfile" && (
          <LawyerProfilePage
            lawyerId={lawyerId}
            onBack={goBackToDashboard}
          />
        )}


      {/* =================================================
          LAWYER — MY ACTIVE CASES
          ================================================= */}

      {session.role === "LAWYER" &&
        page === "lawyerCases" && (
          <LawyerCasesPage
            lawyerId={lawyerId}
            onBack={goBackToDashboard}
            onOpenChat={startChat}
          />
        )}


      {/* =================================================
          ADMIN DASHBOARD
          ================================================= */}

      {session.role === "ADMIN" &&
        page === "adminDashboard" && (
          <AdminDashboardPage
            session={session}
            onSignOut={handleSignOut}
            onNavigate={goToPage}
          />
        )}


      {/* =================================================
          STAFF DASHBOARD
          ================================================= */}

      {session.role === "STAFF" &&
        page === "staffDashboard" && (
          <StaffDashboardPage
            session={session}
            onSignOut={handleSignOut}
            onNavigate={goToPage}
          />
        )}


      {/* =================================================
          SHARED CHAT INBOX (every role)

          pageOwnedByRole() has already proved this role may
          be on "chat" before we render it.
          ================================================= */}

      {page === "chat" && (
        <ChatPage
          session={session}
          onBack={goBackToDashboard}
          target={chatTarget}
          onTargetConsumed={clearChatTarget}
        />
      )}


      {/* =================================================
          SIGN OUT (USER + LAWYER)

          The user and lawyer dashboards predate
          authentication, so the session control is
          provided globally here instead of inside each
          page.
          ================================================= */}

      {(session.role === "USER" ||
        session.role === "LAWYER") && (
        <div className="app-session-bar">
          <span className="app-session-avatar" aria-hidden="true">
            {initialsFromName(session.fullName)}
          </span>

          <div className="app-session-details">
            <LanguageToggle />
            <ThemeToggle />

            <span className="app-session-role">
              {session.role === "LAWYER"
                ? t("app.role.lawyer")
                : t("app.role.user")}
            </span>

            <span className="app-session-name">
              {session.fullName}
            </span>

            <button type="button" onClick={handleSignOut}>
              <LogOut size={13} aria-hidden="true" />
              {t("app.signOut")}
            </button>
          </div>
        </div>
      )}

    </div>
  );
}

export default App;
