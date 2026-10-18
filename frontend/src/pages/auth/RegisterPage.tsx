import { useState } from "react";
import { Scale, User } from "lucide-react";

import { saveLocalLawyerPhoto } from "../../lib/lawyerPhoto";
import type { Session } from "../../auth/session";
import {
  register,
  registerLawyerAccount,
  uploadLawyerDocument,
} from "../../api/authApi";

/*
 * LoginPage's stylesheet defines the whole sign-in visual language
 * (hero, fields, submit, error, note, door cards) — this page
 * reuses it rather than forking the palette, so login and
 * registration stay one visual system.
 */
import "./LoginPage.css";
import { useT } from "../../i18n/context";

/* =========================================================
   REGISTER PAGE — choose an account type, then one form.

   First screen: "Create User Account" OR "Create Lawyer Account".

   - USER form: unchanged citizen self-registration — the server
     assigns USER (a submitted role field is rejected by the
     request model) and signs the person in immediately.
   - LAWYER form: name, email, password, licence/registration ID,
     practice areas, optional profile details and the licence
     document. The account is created PENDING and the document is
     uploaded in the same submission; the confirmation screen says
     so in plain words. There is NO "approve yourself" anywhere:
     verification_status is decided server-side by ADMIN only.
   - ADMIN cannot be self-registered at all, so no admin option
     is ever offered here.

   Client-side validation mirrors the backend's rules so mistakes
   surface instantly; the backend re-checks everything regardless
   (including magic-byte type checks and the size cap on the
   uploaded document).
   ========================================================= */

type RegisterPageProps = {
  onAuthenticated: (session: Session) => void;
  onBack: () => void;
};

type View = "choice" | "user" | "lawyer" | "submitted";

const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const MIN_PASSWORD_LENGTH = 8;

/* Lawyer form bounds — mirrors auth/routes.py + auth/documents.py. */
const MAX_PRACTICE_AREAS = 10;
const MAX_PRACTICE_AREA_LENGTH = 100;
const MAX_BAR_COUNCIL_LENGTH = 200;
const MAX_YEARS_EXPERIENCE = 70;
const MAX_BIO_LENGTH = 1000;
const PHONE_PATTERN = /^[0-9+()\-\s]{5,50}$/;
const MAX_DOCUMENT_BYTES = 10 * 1024 * 1024;
const DOCUMENT_EXTENSIONS = /\.(pdf|jpe?g|png)$/i;
const DOCUMENT_MIME_TYPES = [
  "application/pdf",
  "image/jpeg",
  "image/png",
];

/* Profile photo bounds — client-side validation only; the
   registration API rejects unknown fields, so the photo stays
   on this device until the backend grows a photo endpoint. */
const MAX_PHOTO_BYTES = 2 * 1024 * 1024;
const PHOTO_EXTENSIONS = /\.(jpe?g|png|webp)$/i;
const PHOTO_MIME_TYPES = [
  "image/jpeg",
  "image/png",
  "image/webp",
];

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function RegisterPage({
  onAuthenticated,
  onBack,
}: RegisterPageProps) {
  const { t, tm } = useT();

  const [view, setView] = useState<View>("choice");

  /* Citizen form — unchanged fields. */
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  /* Lawyer form. */
  const [lawName, setLawName] = useState("");
  const [lawEmail, setLawEmail] = useState("");
  const [lawPassword, setLawPassword] = useState("");
  const [lawConfirmation, setLawConfirmation] = useState("");
  const [licenseId, setLicenseId] = useState("");
  const [practiceAreas, setPracticeAreas] = useState("");
  const [barCouncil, setBarCouncil] = useState("");
  const [years, setYears] = useState("");
  const [phone, setPhone] = useState("");
  const [bio, setBio] = useState("");
  const [documentFile, setDocumentFile] =
    useState<File | null>(null);

  /* Profile photo (optional): validated on pick and kept as a
     data URL for the preview and the local save. */
  const [photoDataUrl, setPhotoDataUrl] =
    useState<string | null>(null);
  const [photoError, setPhotoError] = useState("");

  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  /*
   * Set once the LAWYER account exists but before/while the
   * document uploads: a failed upload then never re-runs the
   * registration (the second attempt would collide on the email) —
   * it only retries the upload half of the same submission.
   */
  const [createdSession, setCreatedSession] =
    useState<Session | null>(null);

  const switchView = (next: View) => {
    setError("");
    setView(next);
  };

  /* =======================================================
     CITIZEN SUBMIT
     ======================================================= */

  const handleSubmit = async (
    event: React.FormEvent,
  ) => {
    event.preventDefault();

    if (loading) {
      return;
    }

    const name = fullName.trim();
    const normalizedEmail = email.trim().toLowerCase();

    if (!name) {
      setError(t("register.err.name"));
      return;
    }

    if (!EMAIL_PATTERN.test(normalizedEmail)) {
      setError(t("register.err.email"));
      return;
    }

    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(
        t("register.err.passwordLength", {
          n: MIN_PASSWORD_LENGTH,
        }),
      );
      return;
    }

    if (password !== confirmation) {
      setError(t("register.err.passwordMatch"));
      return;
    }

    setError("");
    setLoading(true);

    try {
      const session = await register({
        fullName: name,
        email: normalizedEmail,
        password,
        passwordConfirmation: confirmation,
      });

      onAuthenticated(session);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : t("register.err.genericUser"),
      );
    } finally {
      setLoading(false);
    }
  };

  /* =======================================================
     PROFILE PHOTO — optional, validated on pick. An invalid
     pick clears the previous valid one, so a broken file can
     never ride along on submit.
     ======================================================= */

  const handlePhotoChange = (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0] ?? null;

    setPhotoError("");

    if (!file) {
      setPhotoDataUrl(null);
      return;
    }

    if (
      !PHOTO_EXTENSIONS.test(file.name) ||
      (file.type && !PHOTO_MIME_TYPES.includes(file.type))
    ) {
      setPhotoDataUrl(null);
      setPhotoError(t("register.err.photoType"));
      return;
    }

    if (file.size > MAX_PHOTO_BYTES) {
      setPhotoDataUrl(null);
      setPhotoError(t("register.err.photoSize"));
      return;
    }

    const reader = new FileReader();

    reader.onload = () => {
      setPhotoDataUrl(
        typeof reader.result === "string"
          ? reader.result
          : null,
      );
    };

    reader.onerror = () => {
      setPhotoDataUrl(null);
      setPhotoError(t("register.err.photoRead"));
    };

    reader.readAsDataURL(file);
  };

  /* =======================================================
     LAWYER SUBMIT — register, then attach the document.
     ======================================================= */

  const handleLawyerSubmit = async (
    event: React.FormEvent,
  ) => {
    event.preventDefault();

    if (loading) {
      return;
    }

    const name = lawName.trim();
    const normalizedEmail = lawEmail.trim().toLowerCase();
    const license = licenseId.trim();
    const areas = practiceAreas
      .split(/[,;]/)
      .map((area) => area.trim())
      .filter(Boolean);
    const council = barCouncil.trim();
    const yearsText = years.trim();
    const phoneText = phone.trim();
    const bioText = bio.trim();

    if (!name) {
      setError(t("register.err.name"));
      return;
    }

    if (!EMAIL_PATTERN.test(normalizedEmail)) {
      setError(t("register.err.email"));
      return;
    }

    if (lawPassword.length < MIN_PASSWORD_LENGTH) {
      setError(
        t("register.err.passwordLength", {
          n: MIN_PASSWORD_LENGTH,
        }),
      );
      return;
    }

    if (lawPassword !== lawConfirmation) {
      setError(t("register.err.passwordMatch"));
      return;
    }

    if (!license) {
      setError(t("register.err.license"));
      return;
    }

    if (!areas.length) {
      setError(t("register.err.practiceMin"));
      return;
    }

    if (areas.length > MAX_PRACTICE_AREAS) {
      setError(
        t("register.err.practiceMax", { n: MAX_PRACTICE_AREAS }),
      );
      return;
    }

    if (
      areas.some(
        (area) => area.length > MAX_PRACTICE_AREA_LENGTH,
      )
    ) {
      setError(
        t("register.err.practiceLength", {
          n: MAX_PRACTICE_AREA_LENGTH,
        }),
      );
      return;
    }

    if (council.length > MAX_BAR_COUNCIL_LENGTH) {
      setError(
        t("register.err.barCouncil", {
          n: MAX_BAR_COUNCIL_LENGTH,
        }),
      );
      return;
    }

    let yearsValue: number | null = null;

    if (yearsText) {
      yearsValue = Number(yearsText);

      if (
        !Number.isInteger(yearsValue) ||
        yearsValue < 0 ||
        yearsValue > MAX_YEARS_EXPERIENCE
      ) {
        setError(
          t("register.err.years", { n: MAX_YEARS_EXPERIENCE }),
        );
        return;
      }
    }

    if (phoneText && !PHONE_PATTERN.test(phoneText)) {
      setError(t("register.err.phone"));
      return;
    }

    if (bioText.length > MAX_BIO_LENGTH) {
      setError(
        t("register.err.bio", { n: MAX_BIO_LENGTH }),
      );
      return;
    }

    if (!documentFile) {
      setError(t("register.err.documentMissing"));
      return;
    }

    if (
      !DOCUMENT_EXTENSIONS.test(documentFile.name) ||
      (documentFile.type &&
        !DOCUMENT_MIME_TYPES.includes(documentFile.type))
    ) {
      setError(t("register.err.documentType"));
      return;
    }

    if (documentFile.size > MAX_DOCUMENT_BYTES) {
      setError(t("register.err.documentSize"));
      return;
    }

    setError("");
    setLoading(true);

    try {
      let session = createdSession;

      if (!session) {
        session = await registerLawyerAccount({
          fullName: name,
          email: normalizedEmail,
          password: lawPassword,
          passwordConfirmation: lawConfirmation,
          licenseId: license,
          practiceAreas: areas.join(", "),
          barCouncil: council || undefined,
          yearsOfExperience: yearsValue,
          phone: phoneText || undefined,
          bio: bioText || undefined,
        });

        setCreatedSession(session);
      }

      await uploadLawyerDocument(session.token, documentFile);

      /*
       * Keep the lawyer's own photo on this device. The
       * registration contract has no profile-photo field yet,
       * so this is the honest local copy the avatar components
       * read as their last-resort source — see lib/lawyerPhoto.ts.
       */
      if (photoDataUrl && session.lawyerId) {
        saveLocalLawyerPhoto(session.lawyerId, photoDataUrl);
      }

      setView("submitted");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : t("register.err.genericLawyer"),
      );
    } finally {
      setLoading(false);
    }
  };

  /* =======================================================
     SHARED HERO
     ======================================================= */

  const hero = (
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
          {t("register.eyebrow")}
        </div>

        <h1>
          {t("register.hero.title1")}
          <br />
          <span>{t("register.hero.titleAccent")}</span>
        </h1>

        <p>{t("register.hero.copy")}</p>

      </div>

    </section>
  );

  /* =======================================================
     VIEW: CHOOSE AN ACCOUNT TYPE
     ======================================================= */

  if (view === "choice") {
    return (
      <div className="login-page login-page--form">

        {hero}

        <main className="login-main login-main--form">

          <div className="login-form">

            <div className="login-form-heading">

              <button
                type="button"
                className="login-back"
                onClick={onBack}
              >
                {t("register.backToSignIn")}
              </button>

              <span className="login-section-label">
                {t("register.choice.label")}
              </span>

              <h2>{t("register.choice.heading")}</h2>

              <p>{t("register.choice.sub")}</p>

            </div>

            <div className="login-door-grid login-door-grid--two">

              <button
                type="button"
                className="login-door-card"
                onClick={() => switchView("user")}
              >
                <div className="login-door-icon"><User size={24} aria-hidden="true" /></div>
                <span className="login-door-role">{t("register.door.citizen.role")}</span>
                <h3>{t("register.door.citizen.title")}</h3>
                <p>{t("register.door.citizen.desc")}</p>
                <div className="login-door-cta">
                  {t("login.door.cta")}
                </div>
              </button>

              <button
                type="button"
                className="login-door-card"
                onClick={() => switchView("lawyer")}
              >
                <div className="login-door-icon"><Scale size={24} aria-hidden="true" /></div>
                <span className="login-door-role">{t("register.door.advocate.role")}</span>
                <h3>{t("register.door.advocate.title")}</h3>
                <p>{t("register.door.advocate.desc")}</p>
                <div className="login-door-cta">
                  {t("login.door.cta")}
                </div>
              </button>

            </div>

            <button
              type="button"
              className="login-staff-link"
              onClick={onBack}
            >
              {t("register.signInLink")}
            </button>

          </div>

        </main>

      </div>
    );
  }

  /* =======================================================
     VIEW: REGISTRATION SUBMITTED (lawyer, pending)
     ======================================================= */

  if (view === "submitted") {
    return (
      <div className="login-page login-page--form">

        {hero}

        <main className="login-main login-main--form">

          <div className="login-form">

            <div className="login-form-heading">

              <span className="login-section-label">
                {t("register.submitted.label")}
              </span>

              <h2>{t("register.submitted.heading")}</h2>

            </div>

            <div
              className="register-pending"
              role="status"
            >

              <strong>{t("register.submitted.status")}</strong>

              <p>{t("register.submitted.copy")}</p>

            </div>

            <button
              type="button"
              className="login-submit"
              onClick={onBack}
            >
              {t("register.submitted.go")}
            </button>

          </div>

        </main>

      </div>
    );
  }

  /* =======================================================
     VIEW: CITIZEN FORM (unchanged)
     ======================================================= */

  if (view === "user") {
    return (
      <div className="login-page login-page--form">

        {hero}

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
                onClick={() => switchView("choice")}
              >
                {t("register.chooseType")}
              </button>

              <span className="login-section-label">
                {t("register.citizen.label")}
              </span>

              <h2>{t("register.citizen.heading")}</h2>

              <p>{t("register.citizen.sub")}</p>

            </div>

            <label className="login-field">

              <span>{t("register.field.fullName")}</span>

              <input
                type="text"
                autoComplete="name"
                placeholder={t("register.field.namePlaceholder.user")}
                value={fullName}
                onChange={(event) =>
                  setFullName(event.target.value)
                }
                autoFocus
              />

            </label>

            <label className="login-field">

              <span>{t("register.field.email")}</span>

              <input
                type="email"
                autoComplete="email"
                placeholder={t("register.field.emailPlaceholder")}
                value={email}
                onChange={(event) =>
                  setEmail(event.target.value)
                }
              />

            </label>

            <label className="login-field">

              <span>{t("login.field.password")}</span>

              <div className="login-password">

                <input
                  type={showPassword ? "text" : "password"}
                  autoComplete="new-password"
                  placeholder={t("register.field.passwordPlaceholder")}
                  value={password}
                  onChange={(event) =>
                    setPassword(event.target.value)
                  }
                />

                <button
                  type="button"
                  aria-label={
                    showPassword ? t("login.password.hide") : t("login.password.show")
                  }
                  aria-pressed={showPassword}
                  onClick={() =>
                    setShowPassword((value) => !value)
                  }
                >
                  {showPassword ? t("login.password.showShort") : t("login.password.hideShort")}
                </button>

              </div>

            </label>

            <label className="login-field">

              <span>{t("register.field.confirm")}</span>

              <input
                type={showPassword ? "text" : "password"}
                autoComplete="new-password"
                placeholder={t("register.field.confirmPlaceholder")}
                value={confirmation}
                onChange={(event) =>
                  setConfirmation(event.target.value)
                }
              />

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
                ? t("register.submit.creating")
                : t("register.submit.create")}
            </button>

            <button
              type="button"
              className="login-staff-link"
              onClick={onBack}
            >
              {t("register.signInLink")}
            </button>

          </form>

        </main>

      </div>
    );
  }

  /* =======================================================
     VIEW: LAWYER FORM
     ======================================================= */

  return (
    <div className="login-page login-page--form">

      {hero}

      <main className="login-main login-main--form">

        <form
          className="login-form"
          onSubmit={handleLawyerSubmit}
          noValidate
          aria-busy={loading}
        >

          <div className="login-form-heading">

            <button
              type="button"
              className="login-back"
              onClick={() => switchView("choice")}
            >
              {t("register.chooseType")}
            </button>

            <span className="login-section-label">
              {t("register.lawyer.label")}
            </span>

            <h2>{t("register.lawyer.heading")}</h2>

            <p>{t("register.lawyer.sub")}</p>

          </div>

          <label className="login-field">

            <span>{t("register.field.fullName")}</span>

            <input
              type="text"
              autoComplete="name"
              placeholder={t("register.field.namePlaceholder.lawyer")}
              value={lawName}
              onChange={(event) =>
                setLawName(event.target.value)
              }
              autoFocus
            />

          </label>

          <label className="login-field">

            <span>{t("register.field.email")}</span>

            <input
              type="email"
              autoComplete="email"
              placeholder={t("register.field.lawEmailPlaceholder")}
              value={lawEmail}
              onChange={(event) =>
                setLawEmail(event.target.value)
              }
            />

          </label>

          <label className="login-field">

            <span>{t("login.field.password")}</span>

            <div className="login-password">

              <input
                type={showPassword ? "text" : "password"}
                autoComplete="new-password"
                placeholder={t("register.field.passwordPlaceholder")}
                value={lawPassword}
                onChange={(event) =>
                  setLawPassword(event.target.value)
                }
              />

              <button
                type="button"
                aria-label={
                  showPassword ? t("login.password.hide") : t("login.password.show")
                }
                aria-pressed={showPassword}
                onClick={() =>
                  setShowPassword((value) => !value)
                }
              >
                {showPassword ? t("login.password.showShort") : t("login.password.hideShort")}
              </button>

            </div>

          </label>

          <label className="login-field">

            <span>{t("register.field.confirm")}</span>

            <input
              type={showPassword ? "text" : "password"}
              autoComplete="new-password"
              placeholder={t("register.field.confirmPlaceholder")}
              value={lawConfirmation}
              onChange={(event) =>
                setLawConfirmation(event.target.value)
              }
            />

          </label>

          <label className="login-field">

            <span>{t("register.field.license")}</span>

            <input
              type="text"
              autoComplete="off"
              placeholder={t("register.field.licensePlaceholder")}
              value={licenseId}
              onChange={(event) =>
                setLicenseId(event.target.value)
              }
            />

          </label>

          <label className="login-field">

            <span>{t("register.field.practiceAreas")}</span>

            <input
              type="text"
              autoComplete="off"
              placeholder={t("register.field.practicePlaceholder")}
              value={practiceAreas}
              onChange={(event) =>
                setPracticeAreas(event.target.value)
              }
            />

            <small>{t("register.field.practiceHint")}</small>

          </label>

          <div className="register-optional-heading">
            {t("register.optional.heading")}
            <span> {t("register.optional.badge")} </span>
          </div>

          <label className="login-field">

            <span>{t("register.field.barCouncil")}</span>

            <input
              type="text"
              autoComplete="organization"
              placeholder={t("register.field.barCouncilPlaceholder")}
              value={barCouncil}
              onChange={(event) =>
                setBarCouncil(event.target.value)
              }
            />

          </label>

          <label className="login-field">

            <span>{t("register.field.years")}</span>

            <input
              type="number"
              min={0}
              max={70}
              placeholder={t("register.field.yearsPlaceholder")}
              value={years}
              onChange={(event) =>
                setYears(event.target.value)
              }
            />

          </label>

          <label className="login-field">

            <span>{t("register.field.phone")}</span>

            <input
              type="tel"
              autoComplete="tel"
              placeholder="+91 98765 43210"
              value={phone}
              onChange={(event) =>
                setPhone(event.target.value)
              }
            />

          </label>

          <label className="login-field">

            <span>{t("register.field.bio")}</span>

            <textarea
              rows={3}
              placeholder={t("register.field.bioPlaceholder")}
              value={bio}
              onChange={(event) =>
                setBio(event.target.value)
              }
            />

          </label>

          <label className="login-field register-file-field">

            <span>{t("register.field.document")}</span>

            <input
              type="file"
              accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
              onChange={(event) =>
                setDocumentFile(
                  event.target.files?.[0] ?? null,
                )
              }
            />

            <small>{t("register.field.documentHint")}</small>

            {documentFile && (
              <small className="register-file-name">
                {documentFile.name} ·{" "}
                {formatSize(documentFile.size)}
              </small>
            )}

          </label>

          <label className="login-field register-file-field">

            <span>{t("register.field.photo")}</span>

            <input
              type="file"
              accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
              onChange={handlePhotoChange}
            />

            <small>{t("register.field.photoHint")}</small>

            {photoError && (
              <small className="register-photo-error">
                {photoError}
              </small>
            )}

            {photoDataUrl && (
              <span className="register-photo-preview">
                <img
                  src={photoDataUrl}
                  alt={t("register.photo.alt")}
                />
              </span>
            )}

          </label>

          {error && (
            <div className="login-error" role="alert">
              {tm(error)}
            </div>
          )}

          {createdSession && !loading && (
            <div className="register-note" role="status">
              {t("register.note.retry")}
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
              ? t("register.submit.submitting")
              : createdSession
                ? t("register.submit.retry")
                : t("register.submit.lawyer")}
          </button>

          <button
            type="button"
            className="login-staff-link"
            onClick={onBack}
          >
            {t("register.signInLink")}
          </button>

        </form>

      </main>

    </div>
  );
}

export default RegisterPage;
