import { useState } from "react";
import { Scale } from "lucide-react";

import CaseSearch from "../../components/CaseSearch";
import CaseDetail from "../../components/CaseDetail";
import CnrLookup from "../../components/CnrLookup";
import type { ChatTarget } from "../../api/chatApi";
import { getCase } from "../../api/caseApi";
import type { Case } from "../../types/case";
import { useT } from "../../i18n/context";

/* =========================================================
   MY CASES

   Two screens behind one door: the list — with the CNR
   lookup above it, which is the only way a case enters
   here — and the matter itself. Keeping them here rather
   than in the router means the hero and the dashboard back
   button belong to the list only — a detail view has its
   own "All cases" link, and two competing back buttons in
   the same corner would be worse than one clear one.

   Each is mounted only while it is on screen, so returning
   to the list re-reads the store and shows whatever was
   saved in the meantime. No screen here creates a court
   case: cases are looked up by CNR and saved, never filed.
   ========================================================= */

type View =
  | { kind: "list" }
  | { kind: "detail"; cnr: string };

type CaseSearchPageProps = {
  /* Signed-in account — the list below is scoped to it, so one user can never
     see another user's cases. */
  userId: string;

  onBack?: () => void;

  /* Opens a chat thread with the advocate on the matter. */
  onChat?: (target: ChatTarget) => void;

  /* Hands the reader to Court Orders — the door an order sent for
     explanation goes through. Omitted where there is no such door,
     and then the order cards simply carry no button. */
  onOpenCourtOrders?: () => void;
};

export default function CaseSearchPage({
  userId,
  onBack,
  onChat,
  onOpenCourtOrders,
}: CaseSearchPageProps) {
  const { t } = useT();

  const [view, setView] = useState<View>({ kind: "list" });

  /* A CNR looked up by number, not yet saved on this account. It
     is kept beside the store rather than inside it: the detail
     view opens on it, but My Cases never starts claiming a matter
     the reader has not chosen to save. */
  const [lookedUp, setLookedUp] = useState<Case | null>(null);

  /* Re-read on every render: the detail view must reflect a
     matter that was re-opened, not the last one it rendered.
     The lookup answer is the fallback when the CNR is not one
     this account saved. */
  const opened =
    view.kind === "detail"
      ? (getCase(view.cnr) ??
        (lookedUp?.cnr_number === view.cnr ? lookedUp : null))
      : null;

  return (
    <main className="nyaymitra-page">
      {/* The dashboard back button belongs to the list. On the
          matter it would sit directly under the component's own
          link and cover it. */}
      {view.kind === "list" && onBack && (
        <div className="page-back-wrapper">
          <button className="page-back-button" onClick={onBack}>
            {t("cases.backToDashboard")}
          </button>
        </div>
      )}

      {view.kind === "list" && (
        <>
          <section className="hero-section">
            <div className="hero-glow" />

            <div className="hero-content">
              <div className="eyebrow">
                <Scale size={15} aria-hidden="true" />
                {t("cases.eyebrow")}
              </div>

              <h1>
                {t("cases.hero.title1")}
                <br />
                <span>{t("cases.hero.titleAccent")}</span>
              </h1>

              <p>{t("cases.hero.copy")}</p>
            </div>
          </section>

          {/* Reading a matter nobody has saved here — the CNR from a
              notice — sits above the account's own list, where the
              person who came for it will find it, with saving left
              as an explicit choice rather than assumed. */}
          <CnrLookup
            userId={userId}
            onOpen={(record) => {
              setLookedUp(record);
              setView({ kind: "detail", cnr: record.cnr_number });
            }}
          />

          <CaseSearch
            userId={userId}
            onOpen={(cnr) => setView({ kind: "detail", cnr })}
          />
        </>
      )}

      {view.kind === "detail" && opened && (
        <CaseDetail
          key={opened.cnr_number}
          caseData={opened}
          userId={userId}
          onBack={() => setView({ kind: "list" })}
          onChat={onChat}
          onOpenCourtOrders={onOpenCourtOrders}
        />
      )}

      {/* A CNR that no longer resolves — the case was removed
          between renders. Drop back to the list rather than
          leaving an empty page. */}
      {view.kind === "detail" && !opened && (
        <section className="matter-detail">
          <button
            type="button"
            className="matter-back"
            onClick={() => setView({ kind: "list" })}
          >
            {t("cases.allCases")}
          </button>

          <div className="matter-empty">
            <span aria-hidden="true"><Scale size={18} /></span>
            <p>{t("cases.gone")}</p>
          </div>
        </section>
      )}
    </main>
  );
}
