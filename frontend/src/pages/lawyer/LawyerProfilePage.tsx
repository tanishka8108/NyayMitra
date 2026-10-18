
import { useEffect, useState } from "react";
import { Scale, Pencil, MapPin, SquarePen } from "lucide-react";
import LawyerAvatar from "../../components/LawyerAvatar";

import {
  getLawyerById,
  editableSnapshot,
  toProfileDraft,
  fromProfileDraft,
  saveProfileEdits,
  PROFILE_SCALAR_FIELDS,
  PROFILE_LIST_FIELDS,
  type ProfileDraft,
  type Lawyer,
} from "../../api/lawyerApi";

import { useT } from "../../i18n/context";
import "./LawyerProfilePage.css";


interface LawyerProfilePageProps {
  lawyerId: string;
  onBack: () => void;
}

/* The edit-form labels come from the api layer (PROFILE_*_FIELDS); map
   their stable field keys to i18n keys so the page can translate them
   at the render site without touching the api module. */
const FIELD_LABEL_KEYS: Record<string, string> = {
  professional_bio: "lawyerProfile.edit.field.professionalBio",
  working_office_hours: "lawyerProfile.edit.field.workingOfficeHours",
  professional_email: "lawyerProfile.edit.field.professionalEmail",
  professional_phone_number: "lawyerProfile.edit.field.professionalPhone",
  office_phone: "lawyerProfile.edit.field.officePhone",
  preferred_contact_method: "lawyerProfile.edit.field.preferredContact",
  website: "lawyerProfile.field.website",
  city: "lawyerProfile.field.city",
  district: "lawyerProfile.field.district",
  state: "lawyerProfile.field.state",
  pincode: "lawyerProfile.field.pincode",
  office_address: "lawyerProfile.edit.field.officeAddress",
  practice_areas: "lawyerProfile.edit.field.practiceAreas",
  courts_of_practice: "lawyerProfile.edit.field.courtsOfPractice",
  languages_known: "lawyerProfile.edit.field.languagesKnown",
  education_qualifications:
    "lawyerProfile.edit.field.educationQualifications",
};

function LawyerProfilePage({
  lawyerId,
  onBack,
}: LawyerProfilePageProps) {
  const { t, tm } = useT();

  const [lawyer, setLawyer] = useState<Lawyer | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  /* Editing works off a copy of the record's own current values,
     so nothing on screen is ever a guess about what the API last
     returned. Every field is held as text — list values are one
     entry per line — until it is saved. */
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<ProfileDraft>({});

  useEffect(() => {
    let cancelled = false;

    async function loadLawyer() {
      try {
        setLoading(true);
        setError("");

       const data = await getLawyerById(lawyerId);

        if (!cancelled) {
          setLawyer(data);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "lawyerProfile.error.load"
          );
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
  }, [lawyerId]);

  const startEditing = () => {
    if (!lawyer) return;

    setDraft(toProfileDraft(editableSnapshot(lawyer)));
    setEditing(true);
  };

  const updateDraft = (key: keyof ProfileDraft, value: string) => {
    setDraft((previous) => ({ ...previous, [key]: value }));
  };

  const cancelEditing = () => {
    setEditing(false);
    setDraft({});
  };

  const saveEditing = () => {
    if (!lawyer) return;

    const patch = fromProfileDraft(draft);

    saveProfileEdits(lawyer.lawyer_id, patch);
    setLawyer({ ...lawyer, ...patch });

    setEditing(false);
    setDraft({});
  };

  if (loading) {
    return (
      <div className="lawyer-profile-page">
        <div className="lawyer-profile-loading">
          <div className="lawyer-profile-spinner" />
          <h2>{t("lawyerProfile.loading.title")}</h2>
          <p>{t("lawyerProfile.loading.copy")}</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="lawyer-profile-page">
        <div className="lawyer-profile-error">
          <div className="lawyer-profile-error-icon">
            !
          </div>

          <h2>{t("lawyerProfile.error.title")}</h2>

          <p>{tm(t(error))}</p>

          <button
            type="button"
            onClick={onBack}
            className="lawyer-profile-back-button"
          >
            {t("lawyerProfile.backToDashboard")}
          </button>
        </div>
      </div>
    );
  }

  if (!lawyer) {
    return (
      <div className="lawyer-profile-page">
        <div className="lawyer-profile-error">
          <h2>{t("lawyerProfile.notFound.title")}</h2>

          <p>{t("lawyerProfile.notFound.copy")}</p>

          <button
            type="button"
            onClick={onBack}
            className="lawyer-profile-back-button"
          >
            {t("lawyerProfile.backToDashboard")}
          </button>
        </div>
      </div>
    );
  }

  /* =========================================================
     EDIT MODE

     Its own screen rather than controls scattered through the
     read-only view: the sections below are laid out to be
     scanned, and input fields dropped between them would turn
     a profile into a form.
     ========================================================= */
  if (editing) {
    return (
      <div className="lawyer-profile-page">

        <section className="lawyer-profile-hero">
          <div className="lawyer-profile-hero-glow" />

          <div className="lawyer-profile-hero-content">

            <button
              type="button"
              onClick={cancelEditing}
              className="lawyer-profile-back"
            >
              {t("lawyerProfile.edit.cancelBack")}
            </button>

            <div className="lawyer-profile-eyebrow">
              <Pencil size={14} aria-hidden="true" />
              {t("lawyerProfile.edit.eyebrow")}
            </div>

            <div className="lawyer-profile-identity">

              <div className="lawyer-profile-avatar">
                <span>{getInitials(lawyer.full_name)}</span>
              </div>

              <div className="lawyer-profile-title">
                <h1>{lawyer.full_name}</h1>

                <p>{t("lawyerProfile.edit.note")}</p>
              </div>

            </div>
          </div>
        </section>

        <main className="lawyer-profile-main">

          <div className="lawyer-edit-panel">

            <div className="lawyer-section-heading">
              <span className="lawyer-section-label">
                {t("lawyerProfile.edit.detailsLabel")}
              </span>

              <h2>{t("lawyerProfile.edit.detailsHeading")}</h2>
            </div>

            <div className="lawyer-edit-note">
              <span>ⓘ</span>

              <p>{t("lawyerProfile.edit.readonlyNote")}</p>
            </div>

            <div className="lawyer-edit-grid">

              {PROFILE_SCALAR_FIELDS.map((field) => (
                <label
                  key={field.key}
                  className={
                    "lawyer-edit-field" +
                    (field.lines ? " is-wide" : "")
                  }
                >
                  <span>{FIELD_LABEL_KEYS[field.key] ? t(FIELD_LABEL_KEYS[field.key]) : field.label}</span>

                  {field.lines ? (
                    <textarea
                      rows={field.lines}
                      value={draft[field.key] ?? ""}
                      onChange={(event) =>
                        updateDraft(field.key, event.target.value)
                      }
                    />
                  ) : (
                    <input
                      type={field.type ?? "text"}
                      value={draft[field.key] ?? ""}
                      onChange={(event) =>
                        updateDraft(field.key, event.target.value)
                      }
                    />
                  )}
                </label>
              ))}

            </div>

            <div className="lawyer-edit-grid">

              {PROFILE_LIST_FIELDS.map((field) => (
                <label
                  key={field.key}
                  className="lawyer-edit-field is-wide"
                >
                  <span>{FIELD_LABEL_KEYS[field.key] ? t(FIELD_LABEL_KEYS[field.key]) : field.label}</span>

                  <textarea
                    rows={4}
                    value={draft[field.key] ?? ""}
                    onChange={(event) =>
                      updateDraft(field.key, event.target.value)
                    }
                  />

                  <small>{t("lawyerProfile.edit.onePerLine")}</small>
                </label>
              ))}

            </div>

            <div className="lawyer-edit-actions">

              <button
                type="button"
                onClick={saveEditing}
                className="lawyer-edit-save"
              >
                {t("lawyerProfile.edit.save")}
              </button>

              <button
                type="button"
                onClick={cancelEditing}
                className="lawyer-edit-cancel"
              >
                {t("lawyerProfile.edit.discard")}
              </button>

            </div>

          </div>

        </main>

      </div>
    );
  }

  return (
    <div className="lawyer-profile-page">

      {/* =====================================================
          HERO
         ===================================================== */}

      <section className="lawyer-profile-hero">
        <div className="lawyer-profile-hero-glow" />

        <div className="lawyer-profile-hero-content">

          <button
            type="button"
            onClick={onBack}
            className="lawyer-profile-back"
          >
            {t("lawyerProfile.back")}
          </button>

          <div className="lawyer-profile-eyebrow">
            <Scale size={15} aria-hidden="true" />
            {t("lawyerProfile.eyebrow")}
          </div>

          <div className="lawyer-profile-identity">

            <LawyerAvatar
              className="lawyer-profile-avatar"
              name={lawyer.full_name}
              photo={
                lawyer.profile_image ?? lawyer.profile_photo
              }
              lawyerId={lawyer.lawyer_id}
            />

            <div className="lawyer-profile-title">
              <h1>{lawyer.full_name}</h1>

              <p>
                {lawyer.practice_areas?.length
                  ? lawyer.practice_areas.join(" • ")
                  : t("lawyerProfile.legalProfessional")}
              </p>

              <div className="lawyer-profile-location">
                <MapPin size={14} aria-hidden="true" />{" "}
                {[
                  lawyer.city,
                  lawyer.district,
                  lawyer.state,
                ]
                  .filter(Boolean)
                  .join(", ") || t("lawyerProfile.locationUnavailable")}
              </div>
            </div>

          </div>
        </div>
      </section>

      {/* =====================================================
          MAIN
         ===================================================== */}

      <main className="lawyer-profile-main">

        {/* EDIT ENTRY */}

        <div className="lawyer-edit-bar">

          <div>

            <span className="lawyer-section-label">
              {t("lawyerProfile.record.label")}
            </span>

            <p>{t("lawyerProfile.record.copy")}</p>

          </div>

          <button
            type="button"
            onClick={startEditing}
          >
            {t("lawyerProfile.editProfile")}
            <SquarePen size={14} aria-hidden="true" />
          </button>

        </div>

        {/* Professional summary */}

        <section className="lawyer-profile-summary">

          <div className="lawyer-summary-item">
            <span>{t("lawyerProfile.summary.experience")}</span>
            <strong>
              {lawyer.years_of_experience ?? "—"}
            </strong>
            <small>{t("lawyerProfile.summary.years")}</small>
          </div>

          <div className="lawyer-summary-item">
            <span>{t("lawyerProfile.summary.enrollmentYear")}</span>
            <strong>
              {lawyer.year_of_enrollment ?? "—"}
            </strong>
            <small>{t("lawyerProfile.summary.barEnrollment")}</small>
          </div>

          <div className="lawyer-summary-item">
            <span>{t("lawyerProfile.summary.barCouncil")}</span>
            <strong>
              {lawyer.bar_council || "—"}
            </strong>
            <small>{t("lawyerProfile.summary.registrationAuthority")}</small>
          </div>

          <div className="lawyer-summary-item">
            <span>{t("lawyerProfile.summary.profileStatus")}</span>
            <strong>
              {lawyer.profile_status || "—"}
            </strong>
            <small>{t("lawyerProfile.summary.currentStatus")}</small>
          </div>

        </section>

        {/* =====================================================
            BASIC INFORMATION
           ===================================================== */}

        <section className="lawyer-profile-section">

          <div className="lawyer-section-heading">
            <span className="lawyer-section-label">
              {t("lawyerProfile.section.basic")}
            </span>

            <h2>{t("lawyerProfile.section.personal")}</h2>
          </div>

          <div className="lawyer-info-grid">

            <InfoItem
              label={t("lawyerProfile.field.lawyerId")}
              value={lawyer.lawyer_id}
            />

            <InfoItem
              label={t("lawyerProfile.field.fullName")}
              value={lawyer.full_name}
            />

            <InfoItem
              label={t("lawyerProfile.field.gender")}
              value={lawyer.gender}
            />

            <InfoItem
              label={t("lawyerProfile.field.dob")}
              value={formatDate(lawyer.date_of_birth)}
            />

          </div>
        </section>

        {/* =====================================================
            PROFESSIONAL INFORMATION
           ===================================================== */}

        <section className="lawyer-profile-section">

          <div className="lawyer-section-heading">
            <span className="lawyer-section-label">
              {t("lawyerProfile.section.professional")}
            </span>

            <h2>{t("lawyerProfile.section.legalPractice")}</h2>
          </div>

          <div className="lawyer-info-grid">

            <InfoItem
              label={t("lawyerProfile.field.enrollmentNumber")}
              value={lawyer.enrollment_number}
            />

            <InfoItem
              label={t("lawyerProfile.field.registrationNumber")}
              value={lawyer.registration_number}
            />

            <InfoItem
              label={t("lawyerProfile.field.barId")}
              value={lawyer.bar_id_or_bar_code}
            />

            <InfoItem
              label={t("lawyerProfile.field.barCouncil")}
              value={lawyer.bar_council}
            />

            <InfoItem
              label={t("lawyerProfile.field.yearOfEnrollment")}
              value={
                lawyer.year_of_enrollment?.toString()
              }
            />

            <InfoItem
              label={t("lawyerProfile.field.yearsOfExperience")}
              value={
                lawyer.years_of_experience !== null &&
                lawyer.years_of_experience !== undefined
                  ? t("lawyerProfile.years", {
                      n: lawyer.years_of_experience,
                    })
                  : null
              }
            />

          </div>

          <div className="lawyer-list-block">

            <span>{t("lawyerProfile.block.practiceAreas")}</span>

            <div className="lawyer-tags">
              {lawyer.practice_areas?.length ? (
                lawyer.practice_areas.map((area) => (
                  <span key={area}>{area}</span>
                ))
              ) : (
                <em>{t("lawyerProfile.notAvailable")}</em>
              )}
            </div>

          </div>

          <div className="lawyer-list-block">

            <span>{t("lawyerProfile.block.courtsOfPractice")}</span>

            <div className="lawyer-tags blue-tags">
              {lawyer.courts_of_practice?.length ? (
                lawyer.courts_of_practice.map((court) => (
                  <span key={court}>{court}</span>
                ))
              ) : (
                <em>{t("lawyerProfile.notAvailable")}</em>
              )}
            </div>

          </div>

        </section>

        {/* =====================================================
            LOCATION
           ===================================================== */}

        <section className="lawyer-profile-section">

          <div className="lawyer-section-heading">
            <span className="lawyer-section-label">
              {t("lawyerProfile.section.officeLocation")}
            </span>

            <h2>{t("lawyerProfile.section.professionalLocation")}</h2>
          </div>

          <div className="lawyer-info-grid">

            <InfoItem
              label={t("lawyerProfile.field.state")}
              value={lawyer.state}
            />

            <InfoItem
              label={t("lawyerProfile.field.district")}
              value={lawyer.district}
            />

            <InfoItem
              label={t("lawyerProfile.field.city")}
              value={lawyer.city}
            />

            <InfoItem
              label={t("lawyerProfile.field.pincode")}
              value={lawyer.pincode}
            />

          </div>

          <div className="lawyer-address-card">

            <span>{t("lawyerProfile.officeAddressLabel")}</span>

            <p>
              {lawyer.office_address ||
                t("lawyerProfile.officeAddressUnavailable")}
            </p>

          </div>

        </section>

        {/* =====================================================
            CONTACT
           ===================================================== */}

        <section className="lawyer-profile-section">

          <div className="lawyer-section-heading">
            <span className="lawyer-section-label">
              {t("lawyerProfile.section.contact")}
            </span>

            <h2>{t("lawyerProfile.section.professionalContact")}</h2>
          </div>

          <div className="lawyer-info-grid">

            <InfoItem
              label={t("lawyerProfile.field.professionalPhone")}
              value={lawyer.professional_phone_number}
            />

            <InfoItem
              label={t("lawyerProfile.field.professionalEmail")}
              value={lawyer.professional_email}
            />

            <InfoItem
              label={t("lawyerProfile.field.officePhone")}
              value={lawyer.office_phone}
            />

            <InfoItem
              label={t("lawyerProfile.field.preferredContact")}
              value={lawyer.preferred_contact_method}
            />

          </div>

          {lawyer.website && (
            <div className="lawyer-website">
              <span>{t("lawyerProfile.field.website")}</span>

              <a
                href={lawyer.website}
                target="_blank"
                rel="noreferrer"
              >
                {lawyer.website}
              </a>
            </div>
          )}

        </section>

        {/* =====================================================
            EDUCATION & LANGUAGES
           ===================================================== */}

        <section className="lawyer-profile-section">

          <div className="lawyer-section-heading">
            <span className="lawyer-section-label">
              {t("lawyerProfile.section.educationLanguages")}
            </span>

            <h2>{t("lawyerProfile.section.qualifications")}</h2>
          </div>

          <div className="lawyer-two-column">

            <div className="lawyer-list-block">
              <span>{t("lawyerProfile.block.education")}</span>

              <div className="lawyer-tags">
                {lawyer.education_qualifications?.length ? (
                  lawyer.education_qualifications.map(
                    (education) => (
                      <span key={education}>
                        {education}
                      </span>
                    )
                  )
                ) : (
                  <em>{t("lawyerProfile.notAvailable")}</em>
                )}
              </div>
            </div>

            <div className="lawyer-list-block">
              <span>{t("lawyerProfile.block.languages")}</span>

              <div className="lawyer-tags green-tags">
                {lawyer.languages_known?.length ? (
                  lawyer.languages_known.map(
                    (language) => (
                      <span key={language}>
                        {language}
                      </span>
                    )
                  )
                ) : (
                  <em>{t("lawyerProfile.notAvailable")}</em>
                )}
              </div>
            </div>

          </div>

        </section>

        {/* =====================================================
            BIO & OFFICE HOURS
           ===================================================== */}

        <section className="lawyer-profile-section">

          <div className="lawyer-section-heading">
            <span className="lawyer-section-label">
              {t("lawyerProfile.section.additional")}
            </span>

            <h2>{t("lawyerProfile.section.overview")}</h2>
          </div>

          <div className="lawyer-bio-card">

            <h3>{t("lawyerProfile.bioLabel")}</h3>

            <p>
              {lawyer.professional_bio ||
                t("lawyerProfile.bioUnavailable")}
            </p>

          </div>

          <div className="lawyer-hours-card">

            <span>{t("lawyerProfile.hoursLabel")}</span>

            <strong>
              {lawyer.working_office_hours ||
                t("lawyerProfile.hoursUnavailable")}
            </strong>

          </div>

        </section>

        <div className="lawyer-profile-footer">
          {t("lawyerProfile.footer")}
        </div>

      </main>
    </div>
  );
}

/* =========================================================
   SMALL HELPERS
   ========================================================= */

function getInitials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || "")
    .join("");
}

function formatDate(
  date?: string | null
): string | null {
  if (!date) return null;

  const parsed = new Date(date);

  if (Number.isNaN(parsed.getTime())) {
    return date;
  }

  return parsed.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function InfoItem({
  label,
  value,
}: {
  label: string;
  value?: string | null;
}) {
  const { t } = useT();

  return (
    <div className="lawyer-info-item">
      <span>{label}</span>
      <strong>{value || t("lawyerProfile.notAvailable")}</strong>
    </div>
  );
}

export default LawyerProfilePage;