import { useEffect, useRef, useState } from "react";
import {
  Mic,
  Square,
  Sparkles,
  Volume2,
  Volume1,
} from "lucide-react";
import type { CSSProperties } from "react";

import { transcribeVoice, translateText } from "../../api/translationApi";
import type { LanguageCode } from "../../api/translationApi";
import { getGuidance } from "../../api/guidanceApi";
import type { GuidanceResult } from "../../api/guidanceApi";

import {
  ModelApiError,
  understandSituation,
  toWhatHappenedView,
} from "../../services/modelApi";
import type { ModelApiErrorKind, WhatHappenedView } from "../../services/modelApi";

import ServiceStatus from "../../components/ServiceStatus";
import "./WhatHappened.css";

/* =========================================================
   TELL US WHAT HAPPENED

   The screen where somebody describes something that happened
   to them, in English, Hindi or Marathi, and gets back what
   the model understood: the intent, the incident category, how
   confident it is, the facts it read out of the text, and what
   it still needs to know.

   One POST does all of that:

       POST /understand-situation   { "text": "..." }

   served by src/api.py. The response is turned into a view by
   toWhatHappenedView() in services/modelApi.ts — that adapter
   is the only place that knows the wire shape, so this file
   deals in intent / category / confidence / facts / missing
   information and nothing else.

   THE UNCLEAR CASE. The pipeline refuses rather than guesses:
   when the confidence or the class margin falls below its
   cut-off it answers intent "unclear" and returns a message
   asking the person to rephrase, with the category, facts and
   missing information all null. In that case this screen shows
   the rephrase prompt and deliberately shows NO category —
   rendering a guess the model declined to make would undo the
   whole point of the guard.

   The guidance panel below the result ("What to do next" and
   the urgency read) still comes from the NLP service on the
   translation port. It is best-effort here: if that service is
   not running it simply does not appear, and the model result
   above it is unaffected.
   ========================================================= */

type VoiceNyayMitraPageProps = {
  onBack: () => void;
};

const languages: { code: LanguageCode; name: string }[] = [
  { code: "en", name: "English" },
  { code: "hi", name: "हिन्दी" },
  { code: "mr", name: "मराठी" },
];

/* The pipeline truncates anything longer than this server-side,
   so the counter says so rather than letting the tail vanish. */
const MAX_TEXT_LENGTH = 1000;

/* =========================================================
   WHAT EACH LANGUAGE ACTUALLY SUPPORTS

   Verified against the real backends, not assumed:

   * The speech-to-text checkpoint the /api/voice endpoint uses
     (ai4bharat/indic-conformer-600m-multilingual) carries a
     language mask for 22 Indian languages — हिन्दी and मराठी
     among them, but NO English. So the microphone transcribes
     हिन्दी and मराठी; English is typed, not spoken. When
     English is chosen the mic says so instead of silently
     sending audio the model cannot read.

   * Read-aloud (browser TTS) works in all three. English is
     spoken as the model answered it. हिन्दी/मराठी summaries
     come back from the model in English, so they are run
     through the existing IndicTrans2 translation service
     first — translation only when it is actually needed. If
     the device has no voice for the chosen language, that is
     said plainly rather than falling back to an English voice.
   ========================================================= */

const ASR_LANGUAGES: LanguageCode[] = ["hi", "mr"];

const LANGUAGE_NAMES: Record<LanguageCode, string> = {
  en: "English",
  hi: "हिन्दी",
  mr: "मराठी",
};

function speechSynthesisSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

/* The Web Speech API can only speak with a voice that exists on the
   device or is shipped by the browser. Pick an explicit matching
   voice; return null when there is none, so the caller can say so
   instead of speaking in the wrong accent or staying silent. */
function pickVoice(code: LanguageCode): SpeechSynthesisVoice | null {
  if (!speechSynthesisSupported()) return null;

  const voices = window.speechSynthesis.getVoices();

  if (!voices.length) return null;

  const wanted = speechLang(code).replace("_", "-");

  return (
    voices.find((voice) => voice.lang.replace("_", "-") === wanted) ||
    voices.find((voice) =>
      voice.lang.replace("_", "-").toLowerCase().startsWith(code),
    ) ||
    null
  );
}

/* Chrome fills its voice list asynchronously; wait once for it. */
function voicesReady(): Promise<SpeechSynthesisVoice[]> {
  if (!speechSynthesisSupported()) return Promise.resolve([]);

  const current = window.speechSynthesis.getVoices();

  if (current.length) return Promise.resolve(current);

  return new Promise((resolve) => {
    let settled = false;

    const finish = () => {
      if (settled) return;
      settled = true;
      window.speechSynthesis.removeEventListener("voiceschanged", finish);
      resolve(window.speechSynthesis.getVoices());
    };

    window.speechSynthesis.addEventListener("voiceschanged", finish);
    window.setTimeout(finish, 1500);
  });
}

/* A clear sentence for "no voice for this language", per language. */
function noVoiceMessage(code: LanguageCode): string {
  if (code === "en") {
    return "No English voice is available on this device, so read aloud cannot speak. Turn on an English (India) speech voice in Windows Settings → Time & language → Speech.";
  }

  return `No ${LANGUAGE_NAMES[code]} voice is available on this device. Install a ${LANGUAGE_NAMES[code]} speech pack from Windows Settings → Time & language → Language & region, or open this page in Microsoft Edge, which ships ${LANGUAGE_NAMES[code]} voices online.`;
}

type Turn = {
  id: string;
  text: string;
  view: WhatHappenedView;
  guidance: GuidanceResult | null;
};

type Failure = {
  kind: ModelApiErrorKind;
  message: string;
};

/* One line per failure kind. The detail underneath is whatever
   the API actually said — never replaced by a guess. */
const FAILURE_TITLES: Record<ModelApiErrorKind, string> = {
  validation: "That text could not be accepted",
  rate_limit: "Too many requests",
  server: "The model could not answer",
  unavailable: "Situation understanding is not available",
  network: "The model service could not be reached",
  unknown: "That could not be read",
};

const EXAMPLES = [
  "Someone called me pretending to be from my bank and asked for my OTP. I gave it and money was deducted.",
  "मेरे खाते से बिना मेरी अनुमति के पैसे कट गए।",
  "माझ्या खात्यातून विना परवानगी पैसे कापले गेले.",
];

/* Carried over from the earlier Next Steps screen. These four
   hold whether or not the guidance set recognised anything. */
const GENERAL_CHECKLIST = [
  {
    title: "Check the next hearing date",
    body: "Review your latest case information and confirm the upcoming hearing date with the court record.",
  },
  {
    title: "Review required documents",
    body: "Check whether any documents, applications or evidence need to be submitted before the next hearing.",
  },
  {
    title: "Consult your lawyer",
    body: "Discuss the latest case development with your lawyer before taking an important legal action.",
  },
  {
    title: "Keep your case information updated",
    body: "Continue monitoring your case status and upcoming hearings through NyayMitra.",
  },
];

const URGENCY_BLURB: Record<string, string> = {
  low: "Nothing in the matched stage calls for immediate action.",
  medium: "The matched stage usually calls for action within a short span.",
  high: "The matched stage usually calls for prompt attention.",
};

let turnSeq = 0;

function nextTurnId(): string {
  turnSeq += 1;
  return `t${turnSeq}`;
}

/* Browser TTS voice for the chosen language. Falls back to the
   default voice when the language has none installed — speaking in
   the wrong accent still beats not speaking at all. */
function speechLang(code: LanguageCode): string {
  if (code === "hi") return "hi-IN";
  if (code === "mr") return "mr-IN";
  return "en-IN";
}

/** What the read-aloud control actually says: the intent, the
 *  category with its confidence, then what was found and what is
 *  still missing. Long enough to be worth hearing, short enough
 *  not to lose the listener. */
function speakable(view: WhatHappenedView): string {
  if (view.isUnclear) {
    return `${view.intentLabel}. ${view.rephraseMessage ?? ""}`.trim();
  }

  const parts = [
    view.intentLabel,
    view.category ? `Category: ${view.category.slug.replace(/_/g, " ")}` : "",
    `Confidence ${view.confidencePercent} percent`,
    ...(view.facts ?? []).map((fact) => `${fact.key}: ${fact.value}`),
    view.missingInformation && view.missingInformation.length > 0
      ? `Still needed: ${view.missingInformation.join(", ")}`
      : "",
  ].filter(Boolean);

  const text = parts.join(". ").replace(/\s+/g, " ").trim();

  return text.length > 900 ? `${text.slice(0, 897)}…` : text;
}

export default function VoiceNyayMitraPage({
  onBack,
}: VoiceNyayMitraPageProps) {
  const [language, setLanguage] = useState<LanguageCode>("en");
  const [question, setQuestion] = useState("");
  const [isListening, setIsListening] = useState(false);
  const [isReading, setIsReading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);

  const audioChunksRef = useRef<Blob[]>([]);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);

  /* Which turn is speaking — one id, so only that card shows
     "Speaking…" and Stop only stops what is actually talking. */
  const [speakingId, setSpeakingId] = useState<string | null>(null);
  /* While a हिन्दी/मराठी summary is being translated for reading. */
  const [preparingId, setPreparingId] = useState<string | null>(null);
  /* Read-aloud could not happen — say why, right on the card. */
  const [ttsNotice, setTtsNotice] = useState<string | null>(null);
  /* The microphone was asked for a language the speech model cannot read. */
  const [micNotice, setMicNotice] = useState<string | null>(null);

  const stopSpeaking = () => {
    if (speechSynthesisSupported()) {
      window.speechSynthesis.cancel();
    }
    setSpeakingId(null);
    setPreparingId(null);
  };

  /* Stop any playback when the page goes away, so a half-read
     answer does not keep talking over the dashboard. */
  useEffect(() => {
    return () => {
      if (speechSynthesisSupported()) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  /* Read aloud in the SELECTED language.

     English is spoken exactly as the model answered it — no
     translation call, because none is needed. A हिन्दी/मराठी
     summary comes back from the model in English, so it goes
     through the existing IndicTrans2 service first, then is
     spoken by the device's हिन्दी/मराठी voice.

     Three things can go wrong, and each is said out loud on
     the page rather than swallowed: no speech synthesis at all,
     no voice for the chosen language, and a translation service
     that did not answer. */
  const speak = async (text: string, turnId: string) => {
    setTtsNotice(null);

    if (!text.trim()) return;

    if (!speechSynthesisSupported()) {
      setTtsNotice(
        "Read aloud is not available — this browser has no speech synthesis.",
      );
      return;
    }

    /* Chrome fills its voice list asynchronously; wait once. */
    await voicesReady();

    const voice = pickVoice(language);

    if (!voice) {
      setTtsNotice(noVoiceMessage(language));
      return;
    }

    let words = text;

    setPreparingId(turnId);

    try {
      if (language !== "en") {
        const translated = await translateText({
          case_id: "",
          source_text: text,
          source_lang: "en",
          target_lang: language,
        });

        words = translated.translated_text || text;
      }
    } catch {
      setPreparingId(null);
      setTtsNotice(
        "The summary could not be translated for read aloud — the translation service did not answer. Try again once it is running, or read the English text above.",
      );
      return;
    }

    setPreparingId(null);

    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(words);

    utterance.voice = voice;
    utterance.lang = speechLang(language);
    /* Set immediately so Stop is available even if the browser
       never fires onstart. */
    setSpeakingId(turnId);
    utterance.onend = () => setSpeakingId(null);
    utterance.onerror = () => {
      setSpeakingId(null);
      setTtsNotice(
        `The ${LANGUAGE_NAMES[language]} voice stopped before finishing — try Read aloud again.`,
      );
    };

    window.speechSynthesis.speak(utterance);
  };

  const blobToWav = async (blob: Blob): Promise<Blob> => {
    const arrayBuffer = await blob.arrayBuffer();

    const audioContext = new AudioContext();
    const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);

    const numberOfChannels = audioBuffer.numberOfChannels;
    const sampleRate = audioBuffer.sampleRate;
    const length = audioBuffer.length;

    const wavBuffer = new ArrayBuffer(44 + length * numberOfChannels * 2);
    const view = new DataView(wavBuffer);

    const writeString = (offset: number, value: string) => {
      for (let i = 0; i < value.length; i++) {
        view.setUint8(offset + i, value.charCodeAt(i));
      }
    };

    writeString(0, "RIFF");
    view.setUint32(4, 36 + length * numberOfChannels * 2, true);
    writeString(8, "WAVE");
    writeString(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, numberOfChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * numberOfChannels * 2, true);
    view.setUint16(32, numberOfChannels * 2, true);
    view.setUint16(34, 16, true);
    writeString(36, "data");
    view.setUint32(40, length * numberOfChannels * 2, true);

    const channels: Float32Array[] = [];

    for (let channel = 0; channel < numberOfChannels; channel++) {
      channels.push(audioBuffer.getChannelData(channel));
    }

    let offset = 44;

    for (let i = 0; i < length; i++) {
      for (let channel = 0; channel < numberOfChannels; channel++) {
        const sample = Math.max(-1, Math.min(1, channels[channel][i]));

        view.setInt16(
          offset,
          sample < 0 ? sample * 0x8000 : sample * 0x7fff,
          true,
        );

        offset += 2;
      }
    }

    await audioContext.close();

    return new Blob([wavBuffer], { type: "audio/wav" });
  };

  const startListening = async () => {
    /* The speech checkpoint behind /api/voice reads 22 Indian
       languages — हिन्दी and मराठी among them, English not among
       them. Rather than record audio the model would refuse,
       say so and let the account be typed. */
    if (!ASR_LANGUAGES.includes(language)) {
      setMicNotice(
        `Speech input in ${LANGUAGE_NAMES[language]} is not available — the speech model transcribes हिन्दी and मराठी only. Type your account in ${LANGUAGE_NAMES[language]} below, or switch the language to speak it.`,
      );
      return;
    }

    setMicNotice(null);

    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error("Microphone access is not supported by this browser.");
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);

      audioChunksRef.current = [];

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());

        const recordedBlob = new Blob(audioChunksRef.current, {
          type: recorder.mimeType,
        });

        const audioBlob = await blobToWav(recordedBlob);

        try {
          setIsReading(true);
          setQuestion("Transcribing your voice...");

          const data = await transcribeVoice(audioBlob, language);

          setQuestion(data.transcribed_text || "");
        } catch (error) {
          console.error("Voice transcription error:", error);

          setQuestion("");

          alert(
            error instanceof Error
              ? error.message
              : "Unable to transcribe the recording.",
          );
        } finally {
          setIsReading(false);
          setIsListening(false);
        }
      };

      mediaRecorderRef.current = recorder;
      recorder.start();
      setIsListening(true);
    } catch (error) {
      console.error("Microphone error:", error);

      setIsListening(false);
      alert("Microphone access was denied or unavailable.");
    }
  };

  const stopListening = () => {
    const recorder = mediaRecorderRef.current;

    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    }
  };

  /*
   * The one call that matters here.
   *
   * Guidance runs alongside it but is never allowed to fail the
   * turn: the model answer is the primary result, and if the NLP
   * service is down the screen still shows everything above.
   */
  const handleAsk = async () => {
    const text = question.trim();

    if (!text || busy) return;

    setBusy(true);
    setFailure(null);

    let view: WhatHappenedView;
    let guidance: GuidanceResult | null = null;

    try {
      view = toWhatHappenedView(await understandSituation(text));
    } catch (caught) {
      const error =
        caught instanceof ModelApiError
          ? caught
          : new ModelApiError(
              caught instanceof Error
                ? caught.message
                : "That could not be read.",
              "unknown",
            );

      setFailure({ kind: error.kind, message: error.message });
      setBusy(false);
      return;
    }

    try {
      guidance = await getGuidance(text);
    } catch {
      /* Optional panel. Missing guidance is not an error. */
      guidance = null;
    }

    setTurns((previous) => [
      ...previous,
      { id: nextTurnId(), text, view, guidance },
    ]);
    setQuestion("");
    setBusy(false);
  };

  const clearConversation = () => {
    stopSpeaking();
    setQuestion("");
    setTurns([]);
    setFailure(null);
    setTtsNotice(null);
    setMicNotice(null);
  };

  const selectedLanguage =
    languages.find((item) => item.code === language)?.name || "English";

  return (
    <main className="voice-nyaymitra-page">
      {/* BACK TO DASHBOARD */}
      <button type="button" className="voice-back-button" onClick={onBack}>
        ← Back to Dashboard
      </button>

      {/* HERO */}
      <section className="voice-hero">
        <div className="voice-hero-glow" />

        <div className="voice-hero-content">
          <div className="voice-eyebrow">
            <Mic size={15} aria-hidden="true" />
            NYAYMITRA VOICE ASSISTANCE
          </div>

          <h1>
            Tell NyayMitra
            <br />
            <span>what happened.</span>
          </h1>

          <p>
            Say what happened in your own words — English, हिन्दी or मराठी.
            NyayMitra reads it back as the intent it understood, the incident
            category, how sure it is, the facts it found and what it still
            needs to know.
          </p>

          <div className="voice-hero-pills">
            <span>Voice First</span>
            <span>Multilingual</span>
            <span>Intent + Category</span>
          </div>
        </div>
      </section>

      {/* MAIN */}
      <section className="voice-main">
        {/* NLP SERVICE STATUS */}
        <ServiceStatus />

        {/* LANGUAGE */}
        <div className="voice-language-card">
          <div>
            <span className="voice-small-label">CONVERSATION LANGUAGE</span>

            <h3>Choose your preferred language</h3>
          </div>

          <select
            value={language}
            onChange={(event) => {
              setLanguage(event.target.value as LanguageCode);
              setMicNotice(null);
              setTtsNotice(null);
            }}
          >
            {languages.map((item) => (
              <option key={item.code} value={item.code}>
                {item.name}
              </option>
            ))}
          </select>
        </div>

        {/* VOICE AREA */}
        <div className="voice-assistant-card">
          <div className="voice-assistant-top">
            <div>
              <span className="voice-section-label">TELL US WHAT HAPPENED</span>

              <h2>What happened?</h2>

              <p>Speak about it, or type what happened below.</p>
            </div>

            <div className="voice-status">
              <span />
              Ready
            </div>
          </div>

          {/* MICROPHONE */}
          <div className="voice-microphone-area">
            <button
              type="button"
              className={
                isListening ? "voice-microphone listening" : "voice-microphone"
              }
              onClick={isListening ? stopListening : startListening}
              aria-label={isListening ? "Stop listening" : "Start voice input"}
            >
              <span>
              {isListening ? (
                <Square size={20} fill="currentColor" aria-hidden="true" />
              ) : (
                <Mic size={22} aria-hidden="true" />
              )}
            </span>
            </button>

            <strong>{isListening ? "Listening..." : "Tap to speak"}</strong>

            <p>
              {isListening
                ? "Tell NyayMitra what has happened"
                : language === "en"
                  ? "Speak in हिन्दी or मराठी — English is typed below"
                  : "Speak naturally in your selected language"}
            </p>

            {/* THE MIC CANNOT READ THIS LANGUAGE — say so here,
                next to the control, instead of failing silently. */}
            {micNotice && (
              <p className="voice-unavailable-note" role="status">
                {micNotice}
              </p>
            )}
          </div>

          {/* WHAT THEY SAID */}
          <div className="voice-input-section">
            <div className="voice-input-heading">
              <label htmlFor="voice-question">WHAT YOU SAID</label>

              {question && !isReading && (
                <button
                  type="button"
                  onClick={() => {
                    setQuestion("");
                    setFailure(null);
                  }}
                >
                  Clear
                </button>
              )}
            </div>

            <textarea
              id="voice-question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Your spoken account will appear here, and you can edit it before sending..."
              rows={5}
            />

            <div className="voice-input-footer">
              <span>
                {question.length} characters
                {question.length > MAX_TEXT_LENGTH
                  ? ` — the first ${MAX_TEXT_LENGTH} are sent`
                  : ""}
              </span>

              <span>{selectedLanguage}</span>
            </div>
          </div>

          {/* ASK BUTTON */}
          <button
            type="button"
            className="voice-ask-button"
            disabled={!question.trim() || busy}
            onClick={handleAsk}
          >
            <Sparkles size={14} aria-hidden="true" />
            {busy ? "Understanding what happened..." : "Tell NyayMitra"}
            <strong>→</strong>
          </button>
        </div>

        {/* EXAMPLES */}
        <div className="voice-example-section">
          <span className="voice-section-label">TRY SAYING</span>

          <h3>Tell NyayMitra...</h3>

          <div className="voice-example-grid">
            {EXAMPLES.map((example) => (
              <button
                type="button"
                key={example}
                onClick={() => setQuestion(example)}
              >
                {example}
              </button>
            ))}
          </div>
        </div>

        {/* IN FLIGHT */}
        {busy && (
          <div className="wh-pending">
            Reading what you described — English, हिन्दी and मराठी are all
            understood.
          </div>
        )}

        {/* FAILURE — by kind, never one generic message */}
        {failure && (
          <div className="voice-disclaimer wh-error">
            <span>ⓘ</span>

            <p>
              <strong>{FAILURE_TITLES[failure.kind]}:</strong> {failure.message}
            </p>
          </div>
        )}

        {/* RESULTS — newest last, so the conversation reads top down */}
        {turns.length > 0 && (
          <div className="wh-transcript">
            {/* READ-ALOUD could not happen — say why, right here */}
            {ttsNotice && (
              <p className="voice-unavailable-note" role="status">
                {ttsNotice}
              </p>
            )}

            {turns.map((turn) => (
              <TurnCard
                key={turn.id}
                turn={turn}
                speaking={speakingId === turn.id}
                preparing={preparingId === turn.id}
                onRead={() => speak(speakable(turn.view), turn.id)}
                onStop={stopSpeaking}
                guidanceSpeaking={speakingId === `${turn.id}-g`}
                guidancePreparing={preparingId === `${turn.id}-g`}
                onReadGuidance={() =>
                  turn.guidance &&
                  speak(
                    turn.guidance.stage
                      ? `${turn.guidance.stage}. ${turn.guidance.what_to_do_next}`
                      : turn.guidance.what_to_do_next,
                    `${turn.id}-g`,
                  )
                }
              />
            ))}
          </div>
        )}

        {turns.length > 0 && (
          <div className="delay-result-actions">
            <button
              type="button"
              className="voice-ask-button"
              onClick={clearConversation}
            >
              <span>↺</span>
              Start a new account
              <strong>→</strong>
            </button>
          </div>
        )}

        {/* DISCLAIMER */}
        <div className="voice-disclaimer">
          <span>ⓘ</span>

          <p>
            <strong>Note:</strong> This reads back what the model understood
            from what you wrote. It is informational only, not legal advice,
            and the exact legal classification depends on the circumstances.
          </p>
        </div>
      </section>
    </main>
  );
}

/* =========================================================
   ONE TURN — what the person said, and what came back.
   ========================================================= */

function TurnCard({
  turn,
  speaking,
  preparing,
  onRead,
  onStop,
  guidanceSpeaking,
  guidancePreparing,
  onReadGuidance,
}: {
  turn: Turn;
  speaking: boolean;
  preparing: boolean;
  onRead: () => void;
  onStop: () => void;
  guidanceSpeaking: boolean;
  guidancePreparing: boolean;
  onReadGuidance: () => void;
}) {
  const { view, guidance } = turn;

  return (
    <>
      {/* WHAT THE PERSON SAID */}
      <div className="wh-turn wh-turn-user">
        <span>YOU</span>
        <p>{turn.text}</p>
      </div>

      {/* WHAT THE MODEL UNDERSTOOD */}
      <div className="wh-turn wh-turn-nyaymitra">
        <div className="wh-answer-head">
          <div className="voice-response-avatar">
            <Sparkles size={20} aria-hidden="true" />
          </div>

          <h3>What we understood</h3>

          <span
            className={`wh-intent-chip${view.isUnclear ? " is-unclear" : ""}`}
          >
            {view.intentLabel}
          </span>

          <button
            type="button"
            className={
              speaking ? "voice-speak-button speaking" : "voice-speak-button"
            }
            onClick={speaking ? onStop : onRead}
          >
            <span>
              {speaking ? (
                <Volume2 size={18} aria-hidden="true" />
              ) : (
                <Volume1 size={18} aria-hidden="true" />
              )}
            </span>
            {speaking
              ? "Speaking…"
              : preparing
                ? "Translating…"
                : "Read aloud"}
          </button>
        </div>

        {/* ---------- UNCLEAR: rephrase, and show no category ---------- */}
        {view.isUnclear ? (
          <div className="wh-panel wh-unclear">
            <span className="wh-panel-title">WE COULD NOT TELL YET</span>

            <p>{view.rephraseMessage}</p>

            <div className="wh-warnings">
              <p>
                No incident category has been assigned, and no facts or missing
                information are shown, because the answer was not confident
                enough to stand behind.
              </p>
            </div>
          </div>
        ) : (
          <>
            {/* ---------- CONFIDENCE ---------- */}
            <div className="wh-panel">
              <span className="wh-panel-title">CONFIDENCE</span>

              <div className="wh-conf">
                <span className="wh-conf-value">
                  {view.confidencePercent}%
                </span>

                <div
                  className="wh-conf-track"
                  role="img"
                  aria-label={`Confidence ${view.confidencePercent} percent`}
                >
                  <div
                    className="wh-conf-fill"
                    style={
                      {
                        "--conf": `${Math.min(100, Math.max(0, view.confidencePercent))}%`,
                      } as CSSProperties
                    }
                  />
                </div>
              </div>

              <p className="wh-conf-note">
                How sure the model is about the intent and category below.
              </p>
            </div>

            {/* ---------- INCIDENT CATEGORY ---------- */}
            <div className="wh-panel">
              <span className="wh-panel-title">INCIDENT CATEGORY</span>

              {view.category ? (
                <p>
                  <span className="wh-category-slug">
                    {view.category.slug.replace(/_/g, " ")}
                  </span>

                  {view.category.id && (
                    <span className="wh-category-id">{view.category.id}</span>
                  )}
                </p>
              ) : (
                <p className="wh-panel-lead">
                  No incident category applies to this message — it reads as a{" "}
                  {view.intentLabel.toLowerCase()} rather than a description of
                  something that happened.
                </p>
              )}
            </div>

            {/* ---------- FACTS ---------- */}
            {view.facts && (
              <div className="wh-panel">
                <span className="wh-panel-title">WHAT WE FOUND IN YOUR ACCOUNT</span>

                <ul className="wh-facts">
                  {view.facts.map((fact) => (
                    <li key={fact.key}>
                      {fact.key}: {fact.value}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* ---------- MISSING INFORMATION → FOLLOW-UP PROMPTS ---------- */}
            {view.missingInformation && (
              <div className="wh-panel wh-panel-gap">
                <span className="wh-panel-title">WHAT WE STILL NEED</span>

                <p className="wh-panel-lead">
                  A little more detail would pin this down. Tell us:
                </p>

                <ul className="wh-missing">
                  {view.missingInformation.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Nothing at all came back: say so rather than show an
                empty card. */}
            {!view.category && !view.facts && !view.missingInformation && (
              <div className="wh-panel">
                <span className="wh-panel-title">DETAILS</span>

                <p className="wh-panel-lead">
                  The model recognised the intent but found no category, facts
                  or follow-up questions for this message.
                </p>
              </div>
            )}
          </>
        )}

        {/* ---------- GUIDANCE (optional, other service) ---------- */}
        {guidance && (
          <GuidanceBlock
            guidance={guidance}
            speaking={guidanceSpeaking}
            preparing={guidancePreparing}
            onRead={onReadGuidance}
            onStop={onStop}
          />
        )}
      </div>
    </>
  );
}

/* =========================================================
   GUIDANCE + URGENCY — unchanged behaviour, now best-effort.
   Rendered only when the NLP service answered.
   ========================================================= */

function GuidanceBlock({
  guidance,
  speaking,
  preparing,
  onRead,
  onStop,
}: {
  guidance: GuidanceResult;
  speaking: boolean;
  preparing: boolean;
  onRead: () => void;
  onStop: () => void;
}) {
  return (
    <>
      <div className="wh-panel">
        <span className="wh-panel-title">
          {guidance.matched ? "MATCHED TO A CASE STAGE" : "WHAT TO DO NEXT"}
        </span>

        <button
          type="button"
          className="voice-ask-button wh-send"
          onClick={speaking ? onStop : onRead}
          style={{ marginTop: 8 }}
        >
          <Volume2 size={16} aria-hidden="true" />
          {speaking ? "Speaking…" : preparing ? "Translating…" : "Read this out"}
        </button>

        <p className="wh-panel-lead">{guidance.what_to_do_next}</p>

        {guidance.matched && (
          <p className="wh-stage">
            Because it looks like this stage: <strong>{guidance.stage}</strong>
            {" — "}
            {guidance.why}
          </p>
        )}

        {guidance.related_terms.length > 0 && (
          <>
            {guidance.related_terms.map((term) => (
              <p key={term.term} className="wh-term">
                <strong>{term.term} —</strong> {term.plain}
              </p>
            ))}
          </>
        )}

        <div className="wh-panel">
          <span className="wh-panel-title">AND ANYWAY</span>

          <ul>
            {GENERAL_CHECKLIST.map((step) => (
              <li key={step.title}>
                <strong>{step.title}:</strong> {step.body}
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="wh-panel">
        <span className="wh-panel-title">URGENCY OF YOUR INCIDENT</span>

        <p>
          {guidance.matched
            ? `${(guidance.urgency ?? "not assessed").toUpperCase()} — ${
                URGENCY_BLURB[guidance.urgency ?? ""] ??
                "No urgency band is recorded for this stage."
              }`
            : "NOT ASSESSED — nothing was recognised, so no band could be borrowed for it."}
        </p>

        <div className="wh-warnings">
          <p>
            {guidance.matched
              ? "This is a lookup describing the matched stage in general, not a model's opinion about this particular incident."
              : "Say a little more — a notice, a hearing date, an order — and the action and the urgency come back together."}
          </p>
        </div>
      </div>

      {guidance.disclaimer && <p className="wh-disclaimer">{guidance.disclaimer}</p>}
    </>
  );
}
