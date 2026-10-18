import { useState } from "react";
import {
  User,
  Scale,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { ROLES, type Role } from "../../auth/roles";
import type { Session } from "../../auth/session";
import { login, DEMO_ACCOUNTS, IS_MOCK_AUTH } from "../../api/authApi";
import { useT } from "../../i18n/context";
import "./LoginPage.css";

/* =========================================================
   LOGIN PAGE

   ONE login system. The user picks the door they belong
   to, and after successful authentication the role on the
   returned session decides which dashboard opens:

       USER   → User dashboard
       LAWYER → Lawyer dashboard
       ADMIN  → Admin dashboard
       STAFF  → Staff dashboard  (staff sign in through
                the Admin door)

   Sign-in talks to the FastAPI auth API by default
   (see api/authApi.ts); VITE_AUTH_MODE=mock keeps the
   offline demo working during development.
   ========================================================= */

type Door = "USER" | "LAWYER" | "ADMIN";

type LoginPageProps = {
  onAuthenticated: (session: Session) => void;

  /* Offered by App while signed out: switch to the register view. */
  onRegister?: () => void;
};

/* =========================================================
   DOOR OPTIONS
   ========================================================= */

const DOORS: Array<{
  door: Door;
  icon: LucideIcon;
  titleKey: string;
  roleKey: string;
  descriptionKey: string;
}> = [
  {
    door: "USER",
    icon: User,
    titleKey: "login.door.user.title",
    roleKey: "login.door.user.role",
    descriptionKey: "login.door.user.desc",
  },
  {
    door: "LAWYER",
    icon: Scale,
    titleKey: "login.door.lawyer.title",
    roleKey: "login.door.lawyer.role",
    descriptionKey: "login.door.lawyer.desc",
  },
  {
    door: "ADMIN",
    icon: ShieldCheck,
    titleKey: "login.door.admin.title",
    roleKey: "login.door.admin.role",
    descriptionKey: "login.door.admin.desc",
  },
];

function LoginPage({
  onAuthenticated,
  onRegister,
}: LoginPageProps) {
  const { t, tm } = useT();

  const [door, setDoor] = useState<Door | null>(null);

  /* Inside the Admin door, staff have their own sign-in. */
  const [staffMode, setStaffMode] = useState(false);

  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const [showDemo, setShowDemo] = useState(false);

  /* =======================================================
     WHICH ROLE ARE WE AUTHENTICATING AS?
     ======================================================= */

  const effectiveRole: Role = staffMode
    ? ROLES.STAFF
    : door || ROLES.USER;

  /* =======================================================
     PICK A DOOR
     ======================================================= */

  const pickDoor = (nextDoor: Door) => {
    setDoor(nextDoor);
    setStaffMode(false);
    setError("");
    setPassword("");
  };

  const backToDoors = () => {
    setDoor(null);
    setStaffMode(false);
    setError("");
    setPassword("");
  };

  /* =======================================================
     SUBMIT
     ======================================================= */

  const handleSubmit = async (
    event: React.FormEvent,
  ) => {
    event.preventDefault();

    if (loading) {
      return;
    }

    /* Client-side checks first: an empty field never costs a
       round trip, and the message appears under the person's
       hands instead of as a server error. The backend still
       validates everything regardless. */
    const trimmedIdentifier = identifier.trim();

    if (!trimmedIdentifier) {
      setError(
        effectiveRole === "STAFF"
          ? t("login.error.staffEmail")
          : t("login.error.identifier"),
      );
      return;
    }

    if (!password) {
      setError(t("login.error.password"));
      return;
    }

    setError("");
    setLoading(true);

    try {
      const session = await login({
        role: effectiveRole,
        identifier: trimmedIdentifier,
        password,
      });

      onAuthenticated(session);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : t("login.error.generic"),
      );
    } finally {
      setLoading(false);
    }
  };

  /* =======================================================
     FILL DEMO CREDENTIALS
     ======================================================= */

  const fillDemo = (email: string, pass: string) => {
    setIdentifier(email);
    setPassword(pass);
    setError("");
  };

  /* =======================================================
     STEP 1 — CHOOSE A DOOR
     ======================================================= */

  if (!door) {
    return (
      <div className="login-page">

        <section className="login-hero">

          <div className="login-hero-glow" />

          <div className="login-hero-content">

            <div className="login-brand">

              <div className="login-brand-icon">
                <Scale size={26} aria-hidden="true" />
              </div>

              <div>
                <strong>NyayMitra</strong>
                <span>{t("login.brand.tagline")}</span>
              </div>

            </div>

            <div className="login-eyebrow">
              {t("login.eyebrow")}
            </div>

            <h1>
              {t("login.hero.title1")}
              <br />
              <span>{t("login.hero.titleAccent")}</span>
            </h1>

            <p>{t("login.hero.copy")}</p>

          </div>

        </section>

        <main className="login-main">

          <div className="login-door-heading">

            <span className="login-section-label">
              {t("login.doors.label")}
            </span>

            <h2>{t("login.doors.heading")}</h2>

            <p>{t("login.doors.sub")}</p>

          </div>

          <div className="login-door-grid">

            {DOORS.map((option) => (
              <button
                key={option.door}
                type="button"
                className="login-door-card"
                onClick={() => pickDoor(option.door)}
              >

                <div className="login-door-icon">
                  <option.icon size={26} aria-hidden="true" />
                </div>

                <span className="login-door-role">
                  {t(option.roleKey)}
                </span>

                <h3>{t(option.titleKey)}</h3>

                <p>{t(option.descriptionKey)}</p>

                <div className="login-door-cta">
                  {t("login.door.cta")}
                </div>

              </button>
            ))}

          </div>

          {onRegister && (
            <button
              type="button"
              className="login-staff-link"
              onClick={onRegister}
            >
              {t("login.registerLink")}
            </button>
          )}

          {IS_MOCK_AUTH && DEMO_ACCOUNTS.length > 0 && (
            <button
              type="button"
              className="login-demo-toggle"
              onClick={() => setShowDemo((value) => !value)}
            >
              {showDemo
                ? t("login.demo.hide")
                : t("login.demo.show")}
            </button>
          )}

          {IS_MOCK_AUTH && DEMO_ACCOUNTS.length > 0 && showDemo && (
            <div className="login-demo-panel">

              <span className="login-section-label">
                {t("login.demo.label")}
              </span>

              <div className="login-demo-list">

                {DEMO_ACCOUNTS.map((account) => (
                  <div
                    key={account.email}
                    className="login-demo-row"
                  >

                    <div>
                      <strong>{account.role}</strong>
                      <span>{account.fullName}</span>
                      <small>
                        {account.email} / {account.password}
                      </small>
                    </div>

                    <button
                      type="button"
                      onClick={() => {
                        /*
                         * STAFF signs in through the
                         * ADMIN door, so a staff demo
                         * account opens the admin door
                         * in staff mode.
                         */
                        const nextDoor: Door =
                          account.role === "STAFF"
                            ? "ADMIN"
                            : (account.role as Door);

                        pickDoor(nextDoor);

                        setStaffMode(
                          account.role === "STAFF",
                        );

                        fillDemo(
                          account.email,
                          account.password,
                        );
                      }}
                    >
                      {t("login.demo.use")}
                    </button>

                  </div>
                ))}

              </div>

            </div>
          )}

        </main>

      </div>
    );
  }

  /* =======================================================
     STEP 2 — CREDENTIALS
     ======================================================= */

  const doorInfo = DOORS.find(
    (option) => option.door === door,
  );

  return (
    <div className="login-page login-page--form">

      <section className="login-hero login-hero--compact">

        <div className="login-hero-glow" />

        <div className="login-hero-content">

          <div className="login-brand">

            <div className="login-brand-icon">
              <Scale size={26} aria-hidden="true" />
            </div>

            <div>
              <strong>NyayMitra</strong>
              <span>{t("login.brand.tagline")}</span>
            </div>

          </div>

          <div className="login-eyebrow">
            {staffMode
              ? t("login.eyebrow.staff")
              : t("login.eyebrow.door", {
                  role: t(doorInfo!.roleKey),
                })}
          </div>

          <h1>
            {staffMode ? (
              <>
                {t("login.staff.title1")}
                <br />
                <span>{t("login.staff.titleAccent")}</span>
              </>
            ) : (
              <>
                {t("login.form.title1")}
                <br />
                <span>{t("login.form.titleAccent")}</span>
              </>
            )}
          </h1>

          <p>
            {staffMode
              ? t("login.staff.desc")
              : t(doorInfo!.descriptionKey)}
          </p>

        </div>

      </section>

      <main className="login-main login-main--form">

        <form
          className="login-form"
          onSubmit={handleSubmit}
          noValidate
          aria-busy={loading}
        >

          <div className="login-form-heading">

            <button
              type="button"
              className="login-back"
              onClick={backToDoors}
            >
              {t("login.back")}
            </button>

            <span className="login-section-label">
              {staffMode
                ? t("login.label.staff")
                : t(doorInfo!.roleKey).toUpperCase()}
            </span>

            <h2>
              {staffMode
                ? t("login.heading.staff")
                : t("login.heading.as", {
                    role: t(doorInfo!.roleKey),
                  })}
            </h2>

            {!staffMode && door === "ADMIN" && (
              <button
                type="button"
                className="login-staff-link"
                onClick={() => {
                  setStaffMode(true);
                  setError("");
                  setPassword("");
                }}
              >
                {t("login.staffLink")}
              </button>
            )}

            {staffMode && (
              <button
                type="button"
                className="login-staff-link"
                onClick={() => {
                  setStaffMode(false);
                  setError("");
                  setPassword("");
                }}
              >
                {t("login.adminBack")}
              </button>
            )}

          </div>

          <label className="login-field">

            <span>
              {effectiveRole === "STAFF"
                ? t("login.field.staffEmail")
                : t("login.field.identifier")}
            </span>

            <input
              type="text"
              name="identifier"
              autoComplete="username"
              placeholder={
                effectiveRole === "STAFF"
                  ? t("login.field.placeholder.staff")
                  : IS_MOCK_AUTH
                    ? t("login.field.placeholder.mock")
                    : t("login.field.placeholder")
              }
              value={identifier}
              onChange={(event) =>
                setIdentifier(event.target.value)
              }
              autoFocus
            />

          </label>

          <label className="login-field">

            <span>{t("login.field.password")}</span>

            <div className="login-password">

              <input
                type={showPassword ? "text" : "password"}
                name="password"
                autoComplete="current-password"
                placeholder={t("login.field.passwordPlaceholder")}
                value={password}
                onChange={(event) =>
                  setPassword(event.target.value)
                }
              />

              <button
                type="button"
                aria-label={
                  showPassword
                    ? t("login.password.hide")
                    : t("login.password.show")
                }
                aria-pressed={showPassword}
                onClick={() =>
                  setShowPassword((value) => !value)
                }
              >
                {showPassword
                  ? t("login.password.hideShort")
                  : t("login.password.showShort")}
              </button>

            </div>

          </label>

          {error && (
            <div className="login-error" role="alert">
              {tm(error)}
            </div>
          )}

          <button
            type="submit"
            className="login-submit"
            disabled={loading}
          >
            {loading && (
              <span className="nm-spinner" aria-hidden="true" />
            )}
            {loading
              ? t("login.submit.loading")
              : staffMode
                ? t("login.submit.staff")
                : t("login.submit.as", {
                    role: t(doorInfo!.roleKey),
                  })}
          </button>

          <p className="login-note">
            {IS_MOCK_AUTH && t("login.note.mock")}
            {t("login.note.tail")}
          </p>

        </form>

      </main>

    </div>
  );
}

export default LoginPage;
