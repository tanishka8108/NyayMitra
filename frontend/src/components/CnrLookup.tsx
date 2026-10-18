import { useState } from "react";
import { Check } from "lucide-react";

import type { Case } from "../types/case";
import { useT, type I18nValue } from "../i18n/context";
import {
  isSavedForUser,
  lookupCaseByCnr,
  saveCaseForUser,
} from "../api/caseApi";

/* =========================================================
   CNR LOOKUP

   My Cases lists what this account saved. A CNR lookup asks
   the case service about any number — the matter an advocate
   mentioned, a hearing notice that arrived by post — and opens
   it for reading. Nothing is saved behind the reader's back:
   the record enters My Cases only through its own explicit
   "Save to My Cases" step, and saving merely tags an existing
   record — it never files a new case.

   The service writes its own refusals: a malformed CNR and an
   unknown CNR read differently, and both are shown as they
   arrive rather than collapsed into one vague "not found".
   A network failure is the third case, and it says the service
   could not be reached instead of implying the number was
   tested and failed.
   ========================================================= */

type CnrLookupProps = {
  /* Signed-in account. Opening never saves; "Save to My Cases"
     tags the record with this account so the detail screen can
     offer the same documents and chat it always does. */
  userId: string;

  /* Hands the resolved record to the page, which opens the detail
     view on it. */
  onOpen: (record: Case) => void;
};

function formatDate(iso: string): string {
  if (!iso) return "—";

  const parsed = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return iso;

  return parsed.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

/* A CNR is four letters identifying the state and court complex, then
   twelve digits ending in the filing year. The same rule the service
   enforces — checked here too, so a wrong number is caught while it is
   still being typed rather than after a request that had no chance. */
const CNR_PATTERN = /^[A-Z]{4}[0-9]{12}$/;

const CNR_EXAMPLE = "MHPU210000042026";

/** What the service does to whatever arrives: uppercase, separators gone. */
function cleanCnr(raw: string): string {
  return raw.toUpperCase().replace(/[\s\-_]/g, "");
}

function cnrHint(query: string, t: I18nValue["t"]): string {
  if (query.length < 16) {
    const missing = 16 - query.length;
    return t("cnr.hintShort", { n: missing });
  }

  if (query.length > 16) {
    return t("cnr.hintLong", { n: query.length - 16 });
  }

  return t("cnr.hintFormat", { example: CNR_EXAMPLE });
}

/* A TypeError is fetch's way of saying the request never left the
   browser. Everything else already carries a sentence written for
   the person reading it. */
function messageFor(
  error: unknown,
  t: I18nValue["t"],
  tm: I18nValue["tm"],
): string {
  if (error instanceof TypeError) {
    return t("cnr.err.offline");
  }

  if (error instanceof Error && error.message.trim()) {
    return tm(error.message);
  }

  return t("cnr.err.notFound");
}

export default function CnrLookup({ userId, onOpen }: CnrLookupProps) {
  const { t, tm } = useT();

  const [cnr, setCnr] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [found, setFound] = useState<Case | null>(null);

  /* The CNR this reader saved most recently. It only forces the
     re-render; the authoritative answer stays with the store, so
     a record saved in an earlier session still reads as saved. */
  const [savedCnr, setSavedCnr] = useState<string | null>(null);

  /* Checked before anything leaves the browser: an empty box and a
     malformed number are answered on the spot, and only a number that
     is shaped like a CNR is sent to the service — which validates it
     again, because a browser's say-so is not a say-so. */
  const query = cleanCnr(cnr);
  const entered = query.length > 0;
  const wellFormed = CNR_PATTERN.test(query);

  const isSaved = found
    ? savedCnr === found.cnr_number ||
      isSavedForUser(found.cnr_number, userId)
    : false;

  const lookup = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (busy) return;

    if (!entered) {
      setFound(null);
      setError(t("cnr.err.empty"));
      return;
    }

    if (!wellFormed) {
      setFound(null);
      setError(t("cnr.err.malformed", { hint: cnrHint(query, t) }));
      return;
    }

    setBusy(true);
    setError(null);
    setFound(null);

    try {
      setFound(await lookupCaseByCnr(query, userId));
    } catch (err) {
      setError(messageFor(err, t, tm));
    } finally {
      setBusy(false);
    }
  };

  /* Saving is a tag on the record the service just returned —
     every field stays as reported; only the owning account is
     set. Saving twice changes nothing (the button is disabled
     once saved), so My Cases never grows duplicates. */
  const save = () => {
    if (!found || isSaved) return;

    saveCaseForUser(found, userId);
    setSavedCnr(found.cnr_number);
  };

  const hearings = found?.case_history_timeline?.length ?? 0;
  const orders = found?.orders?.length ?? 0;

  return (
    <section className="cnr-lookup" aria-labelledby="cnr-lookup-title">
      <div className="cnr-lookup-head">
        <span className="section-label">{t("cnr.label")}</span>

        <h2 id="cnr-lookup-title">{t("cnr.heading")}</h2>

        <p>{t("cnr.intro")}</p>
      </div>

      <form className="cnr-lookup-form" onSubmit={lookup}>
        <div className="cnr-lookup-field">
          <input
            type="text"
            value={cnr}
            onChange={(event) => {
              setCnr(event.target.value.toUpperCase());
              if (error) setError(null);
            }}
            placeholder={CNR_EXAMPLE}
            aria-label={t("cnr.inputLabel")}
            aria-invalid={entered && !wellFormed}
            spellCheck={false}
            autoComplete="off"
            maxLength={24}
          />

          {/* What is still missing, said while the number is being
              typed rather than after a request that could not have
              succeeded. The empty box gets an example instead. */}
          {!entered ? (
            <p className="cnr-lookup-hint">
              {t("cnr.hintEmpty", { example: CNR_EXAMPLE })}
            </p>
          ) : !wellFormed ? (
            <p className="cnr-lookup-hint cnr-lookup-hint-bad">
              {cnrHint(query, t)}
            </p>
          ) : null}
        </div>

        <button type="submit" disabled={!wellFormed || busy}>
          {busy ? t("cnr.busy") : t("cnr.submit")}
        </button>
      </form>

      {error && (
        <p className="cnr-lookup-error" role="alert">
          {error}
        </p>
      )}

      {found && (
        <article className="cnr-result">
          <header className="cnr-result-head">
            <div>
              <span className="detail-label">{t("cases.label.cnr")}</span>
              <h3>{found.cnr_number}</h3>
              <p>
                {found.case_type} · {t("cases.filed")} {formatDate(found.filing_date)}
              </p>
            </div>

            <span className="cnr-result-stage">
              {found.current_case_stage}
            </span>
          </header>

          <div className="cnr-result-grid">
            <div>
              <span className="detail-label">{t("cases.label.petitioner")}</span>
              <strong>{found.petitioner_name}</strong>
            </div>

            <div>
              <span className="detail-label">{t("cases.label.respondents")}</span>
              <strong>{found.respondents_list.join(", ") || "—"}</strong>
            </div>

            <div>
              <span className="detail-label">{t("cases.label.court")}</span>
              <strong>
                {found.court_name}, {found.court_district}
              </strong>
            </div>

            <div>
              <span className="detail-label">{t("cases.label.nextHearing")}</span>
              <strong>{formatDate(found.next_hearing_date)}</strong>
            </div>
          </div>

          <footer className="cnr-result-foot">
            <span className="cnr-result-counts">
              {hearings === 1
                ? t("cnr.hearings.one", { n: hearings })
                : t("cnr.hearings.other", { n: hearings })}
              {" · "}
              {orders === 1
                ? t("cnr.orders.one", { n: orders })
                : t("cnr.orders.other", { n: orders })}
            </span>

            <div className="cnr-result-actions">
              <button
                type="button"
                className="cnr-result-save"
                onClick={save}
                disabled={isSaved}
              >
                {isSaved ? (
                  <>
                    <Check size={13} aria-hidden="true" />
                    {t("cnr.saved")}
                  </>
                ) : (
                  t("cnr.save")
                )}
              </button>

              <button
                type="button"
                className="cnr-result-open"
                onClick={() => onOpen(found)}
              >
                {t("cnr.open")}
                <span aria-hidden="true">→</span>
              </button>
            </div>
          </footer>

          {/* Provenance travels with the record, so this panel never
              reads as a live court feed. */}
          {found.data_source && (
            <p className="cnr-result-source">
              <strong>{found.data_source.label}</strong>{" "}
              {found.data_source.disclaimer}
            </p>
          )}
        </article>
      )}
    </section>
  );
}
