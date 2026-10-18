import { useMemo, useState } from "react";
import { Scale } from "lucide-react";
import { getCasesForUser } from "../api/caseApi";
import { useT } from "../i18n/context";
import CaseCard from "./CaseCard";

type CaseSearchProps = {
  /* Signed-in account. Everything below is scoped to it: the results, the type
     filter and the search box only ever see this user's own saved cases. */
  userId: string;

  /* Opens one matter's detail screen. */
  onOpen?: (cnr: string) => void;
};

export default function CaseSearch({
  userId,
  onOpen,
}: CaseSearchProps) {
  const { t } = useT();

  const [search, setSearch] = useState("");
  const [caseType, setCaseType] = useState("All");

  /* Read on every render, not memoised: saving a case and
     returning to this list must show it without waiting for a
     reload, and the list only rebuilds when something above
     re-renders anyway. */
  const myCases = getCasesForUser(userId);

  const caseTypes = useMemo(() => {
    const types = myCases.map((item) => item.case_type);
    return ["All", ...Array.from(new Set(types))];
  }, [myCases]);

  const filteredCases = useMemo(() => {
    const query = search.toLowerCase().trim();

    return myCases.filter((item) => {
      const matchesSearch =
        !query ||
        item.cnr_number.toLowerCase().includes(query) ||
        item.petitioner_name.toLowerCase().includes(query) ||
        item.case_type.toLowerCase().includes(query) ||
        item.court_name.toLowerCase().includes(query);

      const matchesType =
        caseType === "All" || item.case_type === caseType;

      return matchesSearch && matchesType;
    });
  }, [myCases, search, caseType]);

  return (
    <section className="case-search-section">
      <div className="search-container">

        <div className="search-toolbar">
          <div className="search-box">
            <span className="search-icon">⌕</span>

            <input
              type="text"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t("search.placeholder")}
            />

            {search && (
              <button
                className="clear-search"
                onClick={() => setSearch("")}
                aria-label={t("search.clear")}
              >
                ×
              </button>
            )}
          </div>

          <select
            value={caseType}
            onChange={(event) => setCaseType(event.target.value)}
            className="case-filter"
          >
            {caseTypes.map((type) => (
              <option key={type} value={type}>
                {type === "All" ? t("search.allTypes") : type}
              </option>
            ))}
          </select>
        </div>

        <div className="results-header">
          <div>
            <h2>
              {myCases.length === filteredCases.length
                ? t(
                    myCases.length === 1
                      ? "search.saved.one"
                      : "search.saved.other",
                    { n: myCases.length },
                  )
                : t("search.saved.filtered", {
                    shown: filteredCases.length,
                    total: myCases.length,
                  })}
            </h2>

            <p>
              {search
                ? t("search.showing", { q: search })
                : t("search.noFilter")}
            </p>
          </div>
        </div>

        {filteredCases.length > 0 ? (
          <div className="case-grid">
            {filteredCases.map((caseData) => (
              <CaseCard
                key={caseData.cnr_number}
                caseData={caseData}
                onOpen={onOpen ? () => onOpen(caseData.cnr_number) : undefined}
              />
            ))}
          </div>
        ) : myCases.length === 0 ? (
          /* Nothing saved yet — filtering isn't the problem. */
          <div className="empty-state">
            <div className="empty-icon"><Scale size={24} aria-hidden="true" /></div>
            <h3>{t("search.empty.savedTitle")}</h3>
            <p>{t("search.empty.savedBody")}</p>
          </div>
        ) : (
          <div className="empty-state">
            <div className="empty-icon">⌕</div>
            <h3>{t("search.empty.noneTitle")}</h3>
            <p>{t("search.empty.noneBody")}</p>

            <button
              className="reset-search-btn"
              onClick={() => {
                setSearch("");
                setCaseType("All");
              }}
            >
              {t("search.clear")}
            </button>
          </div>
        )}
      </div>
    </section>
  );
}