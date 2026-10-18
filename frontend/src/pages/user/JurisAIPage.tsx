import { useRef, useState, type FormEvent } from "react";
import {
  ArrowLeft,
  ArrowUp,
  FileText,
  LoaderCircle,
  Mic,
  Paperclip,
  Plus,
  Scale,
  Sparkles,
  X,
} from "lucide-react";
import {
  askWhatHappened,
  type WhatHappenedLanguage,
  type WhatHappenedResponse,
} from "../../api/whatHappenedApi";
import {
  explainOrderUpload,
  type UploadExplainResult,
} from "../../api/courtOrderApi";
import JurisAILiveVoice from "./JurisAILiveVoice";
import "./JurisAIPage.css";
import CourtOrderDetails from "./CourtOrderDetails";

type Props = { onBack: () => void };
type Message =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "assistant"; answer: WhatHappenedResponse }
  | { id: string; role: "assistant"; document: UploadExplainResult };

const languages: { value: WhatHappenedLanguage; label: string }[] = [
  { value: "en", label: "English" },
  { value: "hi", label: "हिन्दी" },
  { value: "mr", label: "मराठी" },
];

const makeId = () =>
  `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

export default function JurisAIPage({ onBack }: Props) {
  const [language, setLanguage] = useState<WhatHappenedLanguage>("en");
  const [mode, setMode] = useState<"incident" | "case">("incident");
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversationId, setConversationId] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [liveVoiceOpen, setLiveVoiceOpen] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const addMessage = (message: Message) => {
    setMessages((current) => [...current, message]);
    window.setTimeout(
      () => endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }),
      50,
    );
  };

  const submitQuestion = async (event?: FormEvent) => {
    event?.preventDefault();
    const text = draft.trim();
    if (!text || busy) return;

    setDraft("");
    setError("");
    addMessage({ id: makeId(), role: "user", text });
    setBusy(true);

    try {
      const result = await askWhatHappened({
        mode,
        text,
        language,
        ...(conversationId ? { conversation_id: conversationId } : {}),
      });
      setConversationId(result.conversation_id);
      addMessage({ id: makeId(), role: "assistant", answer: result });
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Juris AI could not process that question. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  };

  const uploadOrder = async (file?: File) => {
    if (!file || busy) return;
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setError("Please upload a PDF court order.");
      if (fileRef.current) fileRef.current.value = "";
      return;
    }

    setError("");
    addMessage({
      id: makeId(),
      role: "user",
      text: `Please explain this court order: ${file.name}`,
    });
    setBusy(true);

    try {
      const result = await explainOrderUpload(file, language);
      addMessage({ id: makeId(), role: "assistant", document: result });
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The court order could not be explained. Please try again.",
      );
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const startNewChat = () => {
    setMessages([]);
    setConversationId(undefined);
    setDraft("");
    setError("");
    setMode("incident");
  };

  return (
    <main className="juris-page">
      <header className="juris-topbar">
        <button className="juris-icon-button" onClick={onBack} aria-label="Back to dashboard">
          <ArrowLeft size={19} />
        </button>
        <div className="juris-brand">
          <span className="juris-brand-mark"><Scale size={20} /></span>
          <span>
            <strong>Juris AI</strong>
            <small>NyayMitra legal assistant</small>
          </span>
        </div>
        <div className="juris-top-actions">
          <label className="juris-language">
            <span className="sr-only">Response language</span>
            <select
              value={language}
              onChange={(event) => setLanguage(event.target.value as WhatHappenedLanguage)}
              aria-label="Response language"
            >
              {languages.map((item) => (
                <option key={item.value} value={item.value}>{item.label}</option>
              ))}
            </select>
          </label>
          <button className="juris-new-chat" onClick={startNewChat}>
            <Plus size={16} /><span>New chat</span>
          </button>
        </div>
      </header>

      <div className="juris-workspace">
        <aside className="juris-sidebar">
          <div className="juris-sidebar-label">YOUR ASSISTANT</div>
          <button className="juris-side-item active" onClick={startNewChat}>
            <Sparkles size={17} /> Ask Juris AI
          </button>
          <button className="juris-side-item" onClick={() => fileRef.current?.click()}>
            <FileText size={17} /> Explain a court order
          </button>
          <div className="juris-sidebar-note">
            <Scale size={17} />
            <strong>Understand your rights.</strong>
            <p>Get clear explanations of legal processes and possible next steps.</p>
          </div>
          <div className="juris-sidebar-foot">Private legal assistance interface</div>
        </aside>

        <section className="juris-chat" aria-label="Juris AI conversation">
          <div className={`juris-messages ${messages.length ? "has-messages" : ""}`}>
            {messages.length === 0 ? (
              <div className="juris-welcome">
                <div className="juris-welcome-icon"><Sparkles size={27} /></div>
                <div className="juris-eyebrow">YOUR LEGAL COMPANION</div>
                <h1>Let’s make the law<br /><span>easier to understand.</span></h1>
                <p>Tell me what happened, ask about your case, or upload a court order to get a plain-language explanation.</p>
                <div className="juris-mode-switch" role="group" aria-label="Question type">
                  <button
                    className={mode === "incident" ? "selected" : ""}
                    onClick={() => setMode("incident")}
                  >Something happened</button>
                  <button
                    className={mode === "case" ? "selected" : ""}
                    onClick={() => setMode("case")}
                  >My ongoing case</button>
                </div>
                <div className="juris-suggestions">
                  <button onClick={() => setDraft("Help me understand my legal options for a situation I will describe.")}>
                    <span><Scale size={17} /></span>
                    <span><strong>Understand my legal options</strong><small>Explain a situation in simple language</small></span>
                  </button>
                  <button onClick={() => fileRef.current?.click()}>
                    <span><FileText size={17} /></span>
                    <span><strong>Explain a court order</strong><small>Upload a PDF and understand its meaning</small></span>
                  </button>
                  <button onClick={() => setDraft("Explain the usual steps and documents involved in a court case.")}>
                    <span><Sparkles size={17} /></span>
                    <span><strong>Understand court procedure</strong><small>Learn about common steps and documents</small></span>
                  </button>
                </div>
              </div>
            ) : (
              <div className="juris-thread">
                {messages.map((message) => (
                  <article className={`juris-message ${message.role}`} key={message.id}>
                    {message.role === "user" ? (
                      <div className="juris-user-bubble">{message.text}</div>
                    ) : (
                      <div className="juris-answer">
                        {"answer" in message && (
                          <>
                            <div className="juris-answer-heading"><Sparkles size={17} /> Juris AI</div>
                            <section><h3>In simple terms</h3><p>{message.answer.summary}</p></section>
                            {message.answer.possible_issue && (
                              <section><h3>Possible legal issue</h3><p>{message.answer.possible_issue}</p></section>
                            )}
                            {message.answer.explanation && (
                              <section><h3>Explanation</h3><p>{message.answer.explanation}</p></section>
                            )}
                            {message.answer.next_steps?.length > 0 && (
                              <section><h3>Possible next steps</h3><ul>{message.answer.next_steps.map((item, i) => <li key={i}>{item}</li>)}</ul></section>
                            )}
                            {message.answer.follow_up_questions?.length > 0 && (
                              <section><h3>A few follow-up questions</h3><ul>{message.answer.follow_up_questions.map((item, i) => <li key={i}>{item}</li>)}</ul></section>
                            )}
                            {message.answer.warnings?.length > 0 && (
                              <section className="juris-caution"><h3>Important notes</h3><ul>{message.answer.warnings.map((item, i) => <li key={i}>{item}</li>)}</ul></section>
                            )}
                            {message.answer.disclaimer && <p className="juris-disclaimer">{message.answer.disclaimer}</p>}
                          </>
                        )}
                        {"document" in message && (
                          <>
                            <div className="juris-answer-heading"><FileText size={17} /> {message.document.filename}</div>
                            <section><h3>Order summary</h3><p>{message.document.summary}</p></section>
                            <CourtOrderDetails document={message.document} />
                            {message.document.points?.length > 0 && (
                              <section><h3>Important points</h3><ul>{message.document.points.map((point, i) => <li key={i}><strong>{point.heading}: </strong>{point.plain}</li>)}</ul></section>
                            )}
                            {message.document.key_dates?.length > 0 && (
                              <section><h3>Key dates</h3><ul>{message.document.key_dates.map((date, i) => <li key={i}>{date}</li>)}</ul></section>
                            )}
                            {message.document.terms?.length > 0 && (
                              <section><h3>Legal terms explained</h3><ul>{message.document.terms.map((term, i) => <li key={i}><strong>{term.term}: </strong>{term.plain}</li>)}</ul></section>
                            )}
                            {message.document.disclaimer && <p className="juris-disclaimer">{message.document.disclaimer}</p>}
                          </>
                        )}
                      </div>
                    )}
                  </article>
                ))}
                {busy && <div className="juris-thinking"><LoaderCircle size={17} /> Thinking through your request…</div>}
                <div ref={endRef} />
              </div>
            )}
          </div>

          {error && <div className="juris-error" role="alert"><span>{error}</span><button onClick={() => setError("")} aria-label="Dismiss error"><X size={16} /></button></div>}

          {liveVoiceOpen && (
            <JurisAILiveVoice
              language={language}
              onClose={() => setLiveVoiceOpen(false)}
            />
          )}

          <form className="juris-composer-wrap" onSubmit={submitQuestion}>
            <div className="juris-composer">
              <button
                type="button"
                className="juris-attach juris-live-trigger"
                onClick={() => setLiveVoiceOpen((open) => !open)}
                aria-label="Open live voice conversation"
                aria-pressed={liveVoiceOpen}
                disabled={busy}
              ><Mic size={19} /></button>
              <button
                type="button"
                className="juris-attach"
                onClick={() => fileRef.current?.click()}
                aria-label="Upload a court order PDF"
                disabled={busy}
              ><Paperclip size={19} /></button>
              <textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder={mode === "case" ? "Ask about your ongoing case…" : "Describe what happened or ask a legal question…"}
                rows={1}
                aria-label="Message Juris AI"
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void submitQuestion();
                  }
                }}
              />
              <button className="juris-send" type="submit" disabled={!draft.trim() || busy} aria-label="Send message">
                {busy ? <LoaderCircle size={18} className="juris-spin" /> : <ArrowUp size={19} />}
              </button>
            </div>
            <div className="juris-composer-meta">
              <span>AI responses can be incomplete. Verify important decisions with a qualified lawyer.</span>
              <span>Enter to send · Shift + Enter for a new line</span>
            </div>
          </form>
          <input
            ref={fileRef}
            className="juris-hidden-input"
            type="file"
            accept="application/pdf,.pdf"
            onChange={(event) => void uploadOrder(event.target.files?.[0])}
            aria-label="Choose court order PDF"
          />
        </section>
      </div>
    </main>
  );
}
