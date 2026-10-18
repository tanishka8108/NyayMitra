import { useState } from "react";
import {
  Scale,
  Check,
  Languages,
  ArrowRight,
} from "lucide-react";

import {
  simplifyAndTranslate,
  translateText,
  type LegalSimplifyResponse,
} from "../../api/translationApi";

import LegalOrderExplainer from "../../components/LegalOrderExplainer";
import ServiceStatus from "../../components/ServiceStatus";

import { useT } from "../../i18n/context";

type TranslationPageProps = {
  onBack: () => void;
};

type Language = {
  code: "en" | "hi" | "mr";
  /** Dictionary key for the language name shown in the dropdowns. */
  nameKey: string;
  apiCode: "eng_Latn" | "hin_Deva" | "mar_Deva";
};

const languages: Language[] = [
  {
    code: "en",
    nameKey: "trans.lang.en",
    apiCode: "eng_Latn",
  },
  {
    code: "hi",
    nameKey: "trans.lang.hi",
    apiCode: "hin_Deva",
  },
  {
    code: "mr",
    nameKey: "trans.lang.mr",
    apiCode: "mar_Deva",
  },
];

/* =========================================================
   TWO WAYS TO READ THE SAME BOX

   Direct Translation   the text you paste, translated
                        word for word.

   Legal Simplification the pipeline this project added:
                        legal English → plain English →
                        Marathi or Hindi, in three layers
                        you can check against each other.

   The second mode needs its own target, because it can also
   stop at plain English (`eng_Latn`) when the reader only
   wants the wording taken apart.
   ========================================================= */

type Mode = "direct" | "simplify";

const SIMPLIFY_TARGETS: Language[] = [
  { code: "mr", nameKey: "trans.lang.mr", apiCode: "mar_Deva" },
  { code: "hi", nameKey: "trans.lang.hi", apiCode: "hin_Deva" },
  { code: "en", nameKey: "trans.lang.en", apiCode: "eng_Latn" },
];

/* The four development cases. Written out here rather than fetched,
   and labelled as such wherever they are shown: they exercise the
   pipeline, they are not orders from any real case.

   `label` and `note` are read by the visitor, so they are translated.
   `text` deliberately is NOT: it is what lands in the source box and is
   sent to the service, which expects legal English. Translating it would
   feed Marathi into an English-input pipeline, so it stays as written. */
const DEMO_LINES: { labelKey: string; noteKey: string; text: string }[] = [
  {
    labelKey: "trans.demo.line1.label",
    noteKey: "trans.demo.line1.note",
    text: "The matter is adjourned.",
  },
  {
    labelKey: "trans.demo.line2.label",
    noteKey: "trans.demo.line2.note",
    text: "The petitioner is directed to file the reply.",
  },
  {
    labelKey: "trans.demo.line3.label",
    noteKey: "trans.demo.line3.note",
    text: "The application stands disposed of.",
  },
  {
    labelKey: "trans.demo.line4.label",
    noteKey: "trans.demo.line4.note",
    text: "The matter is listed for hearing on 15.10.2026.",
  },
];

export default function TranslationPage({
  onBack,
}: TranslationPageProps) {
  const { t, tm } = useT();

  const [sourceLanguage, setSourceLanguage] =
    useState<"en" | "hi" | "mr">("en");

  const [targetLanguage, setTargetLanguage] =
    useState<"hi" | "mr">("mr");

  const [text, setText] = useState("");

  const [translatedText, setTranslatedText] =
    useState("");

  const [copied, setCopied] =
    useState(false);

  const [loading, setLoading] =
    useState(false);

  const [error, setError] =
    useState("");

  const [mode, setMode] = useState<Mode>("direct");

  const [simplifyTarget, setSimplifyTarget] =
    useState<"en" | "hi" | "mr">("mr");

  const [simplifyResult, setSimplifyResult] =
    useState<LegalSimplifyResponse | null>(null);

  /* Switching modes must not leave the other mode's answer on
     screen — the two produce different things and a stale result
     would be read as belonging to the mode you just picked. */
  const switchMode = (next: Mode) => {
    if (next === mode) return;

    setMode(next);
    setTranslatedText("");
    setSimplifyResult(null);
    setError("");
    setCopied(false);
  };

  const handleSimplify = async () => {
    if (!text.trim()) return;

    const target = SIMPLIFY_TARGETS.find(
      (language) => language.code === simplifyTarget
    );

    if (!target) {
      setError(t("orders.err.lang"));
      return;
    }

    setLoading(true);
    setError("");
    setSimplifyResult(null);
    setCopied(false);

    try {
      setSimplifyResult(
        await simplifyAndTranslate({
          text,
          target_lang: target.apiCode,
        })
      );
    } catch (caught) {
      console.error("Simplification error:", caught);

      setError(
        caught instanceof Error && caught.message
          ? tm(caught.message)
          : t("trans.err.simplify")
      );
    } finally {
      setLoading(false);
    }
  };

  const handleTranslate = async () => {
    if (!text.trim()) return;

    setLoading(true);
    setError("");
    setTranslatedText("");
    setCopied(false);

    if (sourceLanguage === targetLanguage) {
      setTranslatedText(text);
      setLoading(false);
      return;
    }

    const source = languages.find(
      (language) => language.code === sourceLanguage
    );

    const target = languages.find(
      (language) => language.code === targetLanguage
    );

    if (!source || !target) {
      setError(t("orders.err.lang"));
      setLoading(false);
      return;
    }

    try {
      const data = await translateText({
        case_id: "demo-001",
        source_text: text,
        source_lang: sourceLanguage,
        target_lang: targetLanguage,
      });

      setTranslatedText(
        data.translated_text || ""
      );
    } catch (error) {
      console.error(
        "Translation error:",
        error
      );

      setError(
        error instanceof Error && error.message
          ? tm(error.message)
          : t("trans.err.translate")
      );
    } finally {
      setLoading(false);
    }
  };

  /* The service only ever translates INTO Hindi or Marathi
     (LANG_CODE_MAP has no "en"), so an English source has no
     valid counterpart to swap with. */
  const canSwap = sourceLanguage !== "en";

  const handleSwap = () => {
    if (!canSwap) return;

    /* True exchange. targetLanguage is always "hi" | "mr", and the
       guard above narrows sourceLanguage to "hi" | "mr" as well, so
       source and target can never collapse onto the same code. */
    const newSource = targetLanguage;
    const newTarget = sourceLanguage;

    setSourceLanguage(newSource);
    setTargetLanguage(newTarget);

    if (translatedText) {
      setText(translatedText);
      setTranslatedText("");
    }

    setError("");
  };

  const handleClear = () => {
    setText("");
    setTranslatedText("");
    setSimplifyResult(null);
    setCopied(false);
    setError("");
  };

  const handleCopy = async () => {
    if (!translatedText) return;

    try {
      await navigator.clipboard.writeText(
        translatedText
      );

      setCopied(true);

      setTimeout(() => {
        setCopied(false);
      }, 1500);
    } catch {
      setCopied(false);
    }
  };

  const sourceName =
    t(
      languages.find(
        (language) =>
          language.code === sourceLanguage
      )?.nameKey || "trans.lang.en"
    );

  const targetName =
    t(
      languages.find(
        (language) =>
          language.code === targetLanguage
      )?.nameKey || "trans.lang.mr"
    );

  const simplifyTargetName =
    t(
      SIMPLIFY_TARGETS.find(
        (language) => language.code === simplifyTarget
      )?.nameKey || "trans.lang.mr"
    );

  return (
    <main className="translation-page">

      {/* BACK TO DASHBOARD */}
      <div className="page-back-wrapper">
        <button
          type="button"
          className="page-back-button"
          onClick={onBack}
        >
          {t("trans.backToDashboard")}
        </button>
      </div>

      {/* HERO */}
      <section className="translation-hero">

        <div className="translation-hero-glow" />

        <div className="translation-hero-content">

          <div className="translation-hero-badge">
            <Languages aria-hidden="true" size={16} />
            {t("trans.hero.badge")}
          </div>

          <h1>
            {t("trans.hero.title1")}
            <br />
            <span>{t("trans.hero.titleAccent")}</span>
          </h1>

          <p>{t("trans.hero.copy")}</p>

          <div className="translation-language-pills">
            <span>{t("trans.pill.hindi")}</span>
            <span>{t("trans.pill.marathi")}</span>
            <span>{t("trans.pill.legal")}</span>
          </div>

        </div>

      </section>

      {/* MAIN */}
      <section className="translation-main">

        {/* NLP SERVICE STATUS */}
        <ServiceStatus />

        {/* MODE: translate as-is, or run the three layers */}
        <div className="translation-mode-switch" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "direct"}
            className={
              mode === "direct"
                ? "translation-mode is-active"
                : "translation-mode"
            }
            onClick={() => switchMode("direct")}
          >
            {t("trans.mode.direct")}
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={mode === "simplify"}
            className={
              mode === "simplify"
                ? "translation-mode is-active"
                : "translation-mode"
            }
            onClick={() => switchMode("simplify")}
          >
            {t("trans.mode.simplify")}
          </button>
        </div>

        {/* LANGUAGE SELECTOR */}
        <div className="translation-language-card">

          {mode === "simplify" ? (
            /* Simplification always reads legal English, so there is
               no source to choose — only where step three lands. */
            <div className="translation-language-side">
              <span className="translation-small-label">
                {t("trans.step3")}
              </span>

              <select
                value={simplifyTarget}
                onChange={(event) =>
                  setSimplifyTarget(
                    event.target.value as
                      | "en"
                      | "hi"
                      | "mr"
                  )
                }
              >
                {SIMPLIFY_TARGETS.map((language) => (
                  <option
                    key={language.code}
                    value={language.code}
                  >
                    {t(language.nameKey)}
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <>
              <div className="translation-language-side">

                <span className="translation-small-label">
                  {t("trans.sourceLabel")}
                </span>

                <select
                  value={sourceLanguage}
                  onChange={(event) => {
                    const value =
                      event.target.value as
                        | "en"
                        | "hi"
                        | "mr";

                    setSourceLanguage(value);

                    if (value === "hi") {
                      setTargetLanguage("mr");
                    } else if (value === "mr") {
                      setTargetLanguage("hi");
                    } else {
                      setTargetLanguage("mr");
                    }

                    setTranslatedText("");
                    setError("");
                  }}
                >
                  {languages.map((language) => (
                    <option
                      key={language.code}
                      value={language.code}
                    >
                      {t(language.nameKey)}
                    </option>
                  ))}
                </select>

              </div>

              <button
                type="button"
                className="translation-swap-button"
                onClick={handleSwap}
                disabled={!canSwap}
                title={
                  canSwap
                    ? t("trans.swap.title")
                    : t("trans.swap.disabled")
                }
                aria-label={t("trans.swap.title")}
              >
                ⇄
              </button>

              <div className="translation-language-side">

                <span className="translation-small-label">
                  {t("trans.targetLabel")}
                </span>

                <select
                  value={targetLanguage}
                  onChange={(event) =>
                    setTargetLanguage(
                      event.target.value as
                        | "hi"
                        | "mr"
                    )
                  }
                >
                  {languages
                    .filter(
                      (language) =>
                        language.code !==
                        sourceLanguage
                    )
                    .filter(
                      (language) =>
                        language.code !== "en"
                    )
                    .map((language) => (
                      <option
                        key={language.code}
                        value={language.code}
                      >
                        {t(language.nameKey)}
                      </option>
                    ))}
                </select>

              </div>
            </>
          )}

        </div>

        {/* WORKSPACE */}
        <div className="translation-workspace">

          {/* SOURCE */}
          <div className="translation-editor">

            <div className="translation-editor-header">

              <div>
                <span className="translation-editor-label">
                  {t("trans.editor.sourceLabel")}
                </span>

                <strong>
                  {sourceName}
                </strong>
              </div>

              {text && (
                <button
                  type="button"
                  className="translation-text-action"
                  onClick={() =>
                    setText("")
                  }
                >
                  {t("trans.editor.clear")}
                </button>
              )}

            </div>

            <textarea
              value={text}
              onChange={(event) =>
                setText(event.target.value)
              }
              placeholder={t("trans.editor.placeholder")}
            />

            <div className="translation-editor-footer">

              <span>
                {t("trans.editor.chars", { n: text.length })}
              </span>

              <span>
                {t("trans.editor.footer")}
              </span>

            </div>

          </div>

          {/* RESULT */}
          <div className="translation-editor translation-output">

            <div className="translation-editor-header">

              <div>
                <span className="translation-editor-label">
                  {mode === "simplify"
                    ? t("trans.output.labelSimplify")
                    : t("trans.output.labelDirect")}
                </span>

                <strong>
                  {mode === "simplify"
                    ? simplifyTargetName
                    : targetName}
                </strong>
              </div>

              {mode === "direct" && translatedText && (
                <button
                  type="button"
                  className="translation-text-action"
                  onClick={handleCopy}
                >
                  {copied ? (
                    <>
                      <Check size={13} aria-hidden="true" />
                      {t("trans.output.copied")}
                    </>
                  ) : (
                    t("trans.output.copy")
                  )}
                </button>
              )}

            </div>

            <div
              className={
                translatedText || simplifyResult
                  ? "translation-output-text"
                  : "translation-output-text empty"
              }
            >

              {loading ? (
                <>
                  <span className="translation-output-icon">
                    ⟳
                  </span>

                  <span>
                    {mode === "simplify"
                      ? t("trans.busy.simplifying")
                      : t("trans.busy.translating")}
                  </span>

                  <small>{t("trans.busy.pleaseWait")}</small>
                </>
              ) : mode === "simplify" ? (
                simplifyResult ? (
                  <LegalOrderExplainer
                    result={simplifyResult}
                  />
                ) : (
                  <>
                    <span className="translation-output-icon">
                      <Languages aria-hidden="true" />
                    </span>

                    <span>
                      {t("trans.output.emptySimplify")}
                    </span>

                    <small>
                      {t("trans.output.emptySimplifyHint")}
                    </small>
                  </>
                )
              ) : translatedText ? (
                translatedText
              ) : (
                <>
                  <span className="translation-output-icon">
                    <Languages aria-hidden="true" />
                  </span>

                  <span>
                    {t("trans.output.emptyDirect")}
                  </span>

                  <small>
                    {t("trans.output.emptyDirectHint")}
                  </small>
                </>
              )}

            </div>

            <div className="translation-editor-footer">

              <span>
                {t("trans.editor.chars", {
                  n: (mode === "simplify"
                    ? simplifyResult?.translated_text ?? ""
                    : translatedText
                  ).length,
                })}
              </span>

              <span>
                {t("trans.output.footer")}
              </span>

            </div>

          </div>

        </div>

        {/* ERROR */}
        {error && (
          <div
            className="translation-error"
            role="alert"
          >
            {error}
          </div>
        )}

        {/* ACTIONS */}
        <div className="translation-action-row">

          <button
            type="button"
            className="translation-primary-button"
            onClick={
              mode === "simplify"
                ? handleSimplify
                : handleTranslate
            }
            disabled={
              !text.trim() || loading
            }
          >
            <Languages aria-hidden="true" size={18} />

            {loading
              ? mode === "simplify"
                ? t("trans.busy.working")
                : t("trans.busy.translating")
              : mode === "simplify"
                ? t("orders.simplify.sectionLabel")
                : t("trans.action.translate")}

            <ArrowRight aria-hidden="true" size={18} />
          </button>

          <button
            type="button"
            className="translation-secondary-button"
            onClick={handleClear}
          >
            {t("trans.action.again")}
          </button>

        </div>

        {/* DEMO EXAMPLES — the four development cases */}
        {mode === "simplify" && (
          <div className="translation-demo-section">

            <div className="translation-section-heading">

              <div>
                <span className="section-label">
                  {t("trans.demo.label")}
                </span>

                <h2>{t("trans.demo.heading")}</h2>
              </div>

              <p className="translation-demo-note">
                {t("trans.demo.note")}
              </p>

            </div>

            <div className="translation-demo-grid">
              {DEMO_LINES.map((line) => (
                <button
                  type="button"
                  key={line.labelKey}
                  onClick={() => {
                    setText(line.text);
                    setSimplifyResult(null);
                    setError("");
                  }}
                >
                  <strong>{t(line.labelKey)}</strong>
                  <small>{t(line.noteKey)}</small>
                  {/* The sample itself stays in English: it is what gets
                      pasted into the source box and sent to the service. */}
                  <code>{line.text}</code>
                </button>
              ))}
            </div>

          </div>
        )}

        {/* QUICK EXAMPLES */}
        <div className="translation-example-section">

          <div className="translation-section-heading">

            <div>
              <span className="section-label">
                {t("trans.quick.label")}
              </span>

              <h2>{t("trans.quick.heading")}</h2>
            </div>

          </div>

          <div className="translation-example-grid">

            <button
              type="button"
              onClick={() =>
                setText(
                  "The court has directed both parties to appear before the court on the next scheduled hearing date."
                )
              }
            >
              <Scale size={16} aria-hidden="true" />

              <div>
                <strong>{t("trans.example.orders.title")}</strong>

                <small>{t("trans.example.orders.desc")}</small>
              </div>

              <b>→</b>
            </button>

            <button
              type="button"
              onClick={() =>
                setText(
                  "The petitioner is directed to submit the required documents within the prescribed period."
                )
              }
            >
              <span>▤</span>

              <div>
                <strong>{t("trans.example.notices.title")}</strong>

                <small>{t("trans.example.notices.desc")}</small>
              </div>

              <b>→</b>
            </button>

            <button
              type="button"
              onClick={() =>
                setText(
                  "The matter is listed for hearing on the next available date."
                )
              }
            >
              <span>◷</span>

              <div>
                <strong>{t("trans.example.updates.title")}</strong>

                <small>{t("trans.example.updates.desc")}</small>
              </div>

              <b>→</b>
            </button>

          </div>

        </div>

        {/* NOTE */}
        <div className="translation-note">

          <span>ⓘ</span>

          <p>
            <strong>{t("trans.note.important")}</strong>{" "}
            {t("trans.note.copy")}
          </p>

        </div>

      </section>

    </main>
  );
}
