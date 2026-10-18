import type { Case } from "../types/case";
import { Scale, Calendar } from "lucide-react";
import { useT } from "../i18n/context";

interface CaseCardProps {
  caseData: Case;

  /* Opens the matter's detail screen. When omitted the card is
     inert, which keeps the component usable on screens where a
     case is only ever display — the staff and admin lists. */
  onOpen?: () => void;
}

function getStatusClass(stage: string) {
  const value = stage.toLowerCase();

  if (value.includes("argument")) return "status-purple";
  if (value.includes("evidence")) return "status-blue";
  if (value.includes("appearance")) return "status-orange";
  if (value.includes("rent")) return "status-green";

  return "status-gray";
}

export default function CaseCard({ caseData, onOpen }: CaseCardProps) {
  const { t } = useT();

  /* The whole card is the target, not just the footer link: a
     reader scanning their own list clicks the matter they are
     already looking at. The keyboard path is the same one. */
  const open = () => onOpen?.();

  return (
    <article
      className={onOpen ? "case-card case-card-clickable" : "case-card"}
      onClick={onOpen ? open : undefined}
      onKeyDown={
        onOpen
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                open();
              }
            }
          : undefined
      }
      role={onOpen ? "button" : undefined}
      tabIndex={onOpen ? 0 : undefined}
    >
      <div className="case-card-top">
        <div>
          <span className="case-label">{t("cases.label.cnr")}</span>
          <h3>{caseData.cnr_number}</h3>
        </div>

        <span className={`status-badge ${getStatusClass(caseData.current_case_stage)}`}>
          <span className="status-dot" />
          {caseData.current_case_stage}
        </span>
      </div>

      <div className="case-type">
        {caseData.case_type}
      </div>

      <div className="case-parties">
        <div className="party-block">
          <span className="detail-label">{t("cases.label.petitioner")}</span>
          <strong>{caseData.petitioner_name}</strong>
        </div>

        <div className="party-arrow">→</div>

        <div className="party-block">
          <span className="detail-label">{t("cases.label.respondents")}</span>
          <strong>
            {caseData.respondents_list.length === 1
              ? caseData.respondents_list[0]
              : `${caseData.respondents_list[0]} + ${caseData.respondents_list.length - 1}`}
          </strong>
        </div>
      </div>

      <div className="case-divider" />

      <div className="case-info-grid">
        <div className="case-info">
          <span className="info-icon"><Scale size={15} aria-hidden="true" /></span>
          <div>
            <span className="detail-label">{t("cases.label.court")}</span>
            <p>{caseData.court_name}</p>
          </div>
        </div>

        <div className="case-info">
          <span className="info-icon"><Calendar size={15} aria-hidden="true" /></span>
          <div>
            <span className="detail-label">{t("cases.label.nextHearing")}</span>
            <p className="hearing-date">
              {new Date(caseData.next_hearing_date).toLocaleDateString(
                "en-IN",
                {
                  day: "2-digit",
                  month: "short",
                  year: "numeric",
                }
              )}
            </p>
          </div>
        </div>
      </div>

      <div className="case-card-footer">
        <span>
          {t("cases.card.advocate")}{" "}<strong>{caseData.petitioner_advocate}</strong>
        </span>

        <button
          className="view-case-btn"
          type="button"
          onClick={(event) => {
            /* Same destination as the card around it — without
               stopping here the click would land twice. */
            event.stopPropagation();
            open();
          }}
        >
          {t("cases.card.view")}
          <span>→</span>
        </button>
      </div>
    </article>
  );
}