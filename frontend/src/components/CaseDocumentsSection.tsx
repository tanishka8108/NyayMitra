import { useCallback, useEffect, useState } from "react";
import { FileText, FolderOpen } from "lucide-react";

import {
  fetchCaseDocuments,
  type CaseDocumentsResult,
} from "../api/caseDocumentApi";
import { useT } from "../i18n/context";

/* =========================================================
   COURT DOCUMENTS — the case service's own files

   Sits on the matter beside the citizen's uploads (Case
   documents) and the docket entries (Orders passed), and is
   the one place that deals in actual files from the backend.

   It is deliberately strict about what it claims:
   - a title, date or size renders only if the API sent it;
   - View / Download are live only for a genuine authorized
     URL from the response — otherwise the row says the file
     is not available, rather than offering a dead button;
   - "not connected", "signed out", "no access" and "failed"
     are four different sentences, because they are four
     different truths;
   - demo rows (development only) carry a DEMO chip and banner
     so sample data can never pass itself off as a record.

   Browser-store cases have no service behind them, so with
   enabled=false the section renders nothing at all.
   ========================================================= */

type CaseDocumentsSectionProps = {
  cnr: string;

  /* True only for cases read from the case service — the one
     place a court document could actually come from. */
  enabled: boolean;
};

function formatDate(iso: string): string {
  const parsed = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return iso;

  return parsed.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function CaseDocumentsSection({
  cnr,
  enabled,
}: CaseDocumentsSectionProps) {
  const { t } = useT();

  /*
   * The answer is stored with the request key it belongs to.
   * While `reloadKey` is newer than the loaded one the screen
   * reads "still loading" — derived during render, which keeps
   * the effect free of synchronous state updates. A retry
   * bumps the key, so the old answer stops showing immediately
   * and the next resolution replaces it.
   */
  const [loaded, setLoaded] = useState<{
    key: number;
    result: CaseDocumentsResult;
  } | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!enabled) return undefined;

    let cancelled = false;

    fetchCaseDocuments(cnr)
      .then((answer) => {
        if (!cancelled) setLoaded({ key: reloadKey, result: answer });
      })
      .catch(() => {
        /* fetchCaseDocuments never rejects today; this keeps the
           screen safe even if the module changes later. */
        if (!cancelled) {
          setLoaded({
            key: reloadKey,
            result: { status: "error", records: [], demo: false },
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [cnr, enabled, reloadKey]);

  const retry = useCallback(() => {
    setReloadKey((key) => key + 1);
  }, []);

  if (!enabled) return null;

  const result =
    loaded && loaded.key === reloadKey ? loaded.result : null;
  const busy = result === null;

  return (
    <article
      className="matter-card matter-court-documents"
      aria-busy={busy}
    >
      <div className="matter-card-head">
        <div>
          <h3>{t("docs.title")}</h3>
          <p>{t("docs.copy")}</p>
        </div>

        {result?.demo && (
          <span
            className="cdoc-chip"
            title={t("docs.demoChipTitle")}
          >
            {t("docs.demoChip")}
          </span>
        )}
      </div>

      {result?.demo && (
        <p className="cdoc-demo" role="note">
          <strong>{t("docs.demoStrong")}</strong> {t("docs.demoBody")}
        </p>
      )}

      {/* ---- loading ---- */}
      {busy && (
        <p className="cdoc-state" role="status">
          <span className="nm-spinner" aria-hidden="true" />
          {t("docs.loading")}
        </p>
      )}

      {/* ---- records: render only what arrived ---- */}
      {result?.status === "ready" && (
        <ul className="cdoc-list">
          {result.records.map((record) => {
            const meta = [
              record.document_type,
              record.issued_at ? formatDate(record.issued_at) : null,
              record.file_name,
              record.size_bytes !== undefined
                ? formatSize(record.size_bytes)
                : null,
            ]
              .filter(Boolean)
              .join(" · ");

            return (
              <li key={record.id} className="cdoc-item">
                <span className="cdoc-icon" aria-hidden="true">
                  <FileText size={18} />
                </span>

                <div className="cdoc-meta">
                  <strong>{record.title}</strong>
                  {meta && <span>{meta}</span>}
                </div>

                <div className="cdoc-actions">
                  {record.view_url ? (
                    <a
                      className="doc-ghost"
                      href={record.view_url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {t("docs.view")}
                    </a>
                  ) : (
                    <span
                      className="cdoc-na"
                      title={t("docs.noViewTitle")}
                    >
                      {t("docs.viewUnavailable")}
                    </span>
                  )}

                  {record.download_url ? (
                    <a
                      className="doc-ghost"
                      href={record.download_url}
                      download
                    >
                      {t("docs.download")}
                    </a>
                  ) : (
                    <span
                      className="cdoc-na"
                      title={t("docs.noDownloadTitle")}
                    >
                      {t("docs.downloadUnavailable")}
                    </span>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {/* ---- none published yet ---- */}
      {result?.status === "empty" && (
        <div className="matter-empty">
          <span aria-hidden="true"><FileText size={20} /></span>
          <p>{t("docs.empty")}</p>
        </div>
      )}

      {/* ---- API not connected / CNR unknown to it ---- */}
      {result?.status === "unavailable" && (
        <div className="matter-empty">
          <span aria-hidden="true"><FolderOpen size={20} /></span>
          <p>{t("docs.unavailable")}</p>
          <small className="cdoc-note">{t("docs.unavailableNote")}</small>
        </div>
      )}

      {/* ---- session ---- */}
      {result?.status === "signed-out" && (
        <p className="cdoc-state" role="status">
          {t("docs.signedOut")}
        </p>
      )}

      {/* ---- access ---- */}
      {result?.status === "forbidden" && (
        <p className="cdoc-state" role="status">
          {t("docs.forbidden")}
        </p>
      )}

      {/* ---- failure, with a way back ---- */}
      {result?.status === "error" && (
        <p className="cdoc-state cdoc-state-error" role="alert">
          {t("docs.error")}
          <button type="button" className="doc-ghost" onClick={retry}>
            {t("docs.retry")}
          </button>
        </p>
      )}
    </article>
  );
}
