import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import VoiceNyayMitraPage from "./VoiceNyayMitraPage";
import { ModelApiError, understandSituation } from "../../services/modelApi";
import { getGuidance } from "../../api/guidanceApi";
import type { GuidanceResult } from "../../api/guidanceApi";
import { transcribeVoice, translateText } from "../../api/translationApi";

const mockedTranscribe = vi.mocked(transcribeVoice);
const mockedTranslate = vi.mocked(translateText);

/* =========================================================
   TELL US WHAT HAPPENED — screen-level acceptance after the
   merge with Member 2's model integration.

   The model client is mocked; the real adapter
   (toWhatHappenedView) runs, so what is under test is this
   page's own behaviour around POST /understand-situation:

     * nothing is sent on arrival;
     * a description comes back as intent / category /
       confidence / facts / missing information panels;
     * the unclear case shows the rephrase prompt and never
       renders a category the model declined to assign;
     * each failure kind gets its own title, and a guidance
       outage never costs the model result;
     * the microphone and read-aloud are playback actions —
       neither sends anything by itself.
   ========================================================= */

vi.mock("../../services/modelApi", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../services/modelApi")>();

  return { ...actual, understandSituation: vi.fn() };
});

vi.mock("../../api/guidanceApi", () => ({
  getGuidance: vi.fn(),
}));

vi.mock("../../api/translationApi", () => ({
  transcribeVoice: vi.fn(),
  translateText: vi.fn(),
}));

vi.mock("../../components/ServiceStatus", () => ({
  default: () => null,
}));

type Wire = Awaited<ReturnType<typeof understandSituation>>;

/* Exactly what POST /understand-situation returned in the live
   API tests — fed through the real view adapter. */
const INCIDENT_WIRE: Wire = {
  intent: "incident",
  incident_category: "threats_intimidation_or_intentional_insult",
  category_id: "INC011",
  confidence: 0.632,
  facts: { threat: "threatened", "date/time": "last night" },
  missing_information: ["person involved", "witnesses"],
  message: null,
};

const UNCLEAR_WIRE: Wire = {
  intent: "unclear",
  incident_category: null,
  category_id: null,
  confidence: 0.29,
  facts: null,
  missing_information: null,
  message:
    "I could not understand that confidently. Please rephrase your message or add a few more details about what happened.",
};

const GUIDANCE: GuidanceResult = {
  matched: true,
  stage: "Case adjourned for want of time",
  urgency: "medium",
  why: "the words used match that stage",
  what_to_do_next: "Confirm the next hearing date with the court record.",
  related_terms: [{ term: "adjourn", plain: "postponed to another day" }],
  candidates: [],
  disclaimer: "General legal information, not legal advice.",
};

const mockedUnderstand = vi.mocked(understandSituation);
const mockedGuidance = vi.mocked(getGuidance);

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

const typeAndSend = (text: string) => {
  fireEvent.change(screen.getByLabelText("WHAT YOU SAID"), {
    target: { value: text },
  });
  fireEvent.click(screen.getByRole("button", { name: /tell nyaymitra/i }));
};

/* ---------------- arrival ---------------- */

describe("entry screen", () => {
  it("offers the composer and calls nothing yet", () => {
    render(<VoiceNyayMitraPage onBack={vi.fn()} />);

    expect(
      screen.getByRole("heading", { name: /what happened\?/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/say what happened in your own words/i),
    ).toBeInTheDocument();

    // One language selector, the microphone, an empty composer.
    expect(screen.getAllByRole("combobox")).toHaveLength(1);
    expect(screen.getByLabelText("Start voice input")).toBeInTheDocument();
    expect(screen.getByLabelText("WHAT YOU SAID")).toBeInTheDocument();

    expect(mockedUnderstand).not.toHaveBeenCalled();
  });
});

/* ---------------- the model call ---------------- */

describe("understand-situation flow", () => {
  it("sends the description and renders what the model understood", async () => {
    mockedUnderstand.mockResolvedValue(INCIDENT_WIRE);
    mockedGuidance.mockRejectedValue(new Error("guidance down"));

    render(<VoiceNyayMitraPage onBack={vi.fn()} />);
    typeAndSend("Someone threatened me and demanded money from me.");

    await waitFor(() =>
      expect(mockedUnderstand).toHaveBeenCalledWith(
        "Someone threatened me and demanded money from me.",
      ),
    );

    // The panels, in the model's own vocabulary.
    expect(await screen.findByText("CONFIDENCE")).toBeInTheDocument();
    expect(screen.getByText("INCIDENT CATEGORY")).toBeInTheDocument();
    expect(
      screen.getByText("threats intimidation or intentional insult"),
    ).toBeInTheDocument();
    expect(screen.getByText("INC011")).toBeInTheDocument();
    expect(screen.getByText(/threat:\s*threatened/i)).toBeInTheDocument();
    expect(screen.getByText("person involved")).toBeInTheDocument();

    // The chip carries the intent.
    expect(document.querySelector(".wh-intent-chip")).not.toBeNull();
  });

  it("the unclear case rephrases and never invents a category", async () => {
    mockedUnderstand.mockResolvedValue(UNCLEAR_WIRE);
    mockedGuidance.mockRejectedValue(new Error("guidance down"));

    render(<VoiceNyayMitraPage onBack={vi.fn()} />);
    typeAndSend("xq9#vZ!pla?42 42 42 asdfghjkl;qwerty");

    expect(
      await screen.findByText(/i could not understand that confidently/i),
    ).toBeInTheDocument();
    expect(screen.getByText("WE COULD NOT TELL YET")).toBeInTheDocument();

    // The guard: no category, no facts, no missing-information panel.
    expect(screen.queryByText("INCIDENT CATEGORY")).not.toBeInTheDocument();
    expect(
      screen.queryByText("WHAT WE FOUND IN YOUR ACCOUNT"),
    ).not.toBeInTheDocument();
    expect(document.querySelector(".wh-intent-chip.is-unclear")).not.toBeNull();
  });

  it("keeps the answers on a language switch and only sends the text", async () => {
    mockedUnderstand.mockResolvedValue(INCIDENT_WIRE);
    mockedGuidance.mockRejectedValue(new Error("guidance down"));

    render(<VoiceNyayMitraPage onBack={vi.fn()} />);
    typeAndSend("Someone threatened me and demanded money from me.");
    expect(await screen.findByText("CONFIDENCE")).toBeInTheDocument();

    // Switch to मराठी — the answer stays, nothing re-sends.
    const languageSelect = screen.getAllByRole("combobox")[0];
    fireEvent.change(languageSelect, { target: { value: "mr" } });
    expect(languageSelect).toHaveValue("mr");
    expect(screen.getAllByText("CONFIDENCE")).toHaveLength(1);
    expect(mockedUnderstand).toHaveBeenCalledTimes(1);

    // The next turn goes out as text alone — no conversation to lose.
    typeAndSend("Someone broke the window of my shop last night.");
    await waitFor(() => expect(mockedUnderstand).toHaveBeenCalledTimes(2));
    expect(mockedUnderstand).toHaveBeenLastCalledWith(
      "Someone broke the window of my shop last night.",
    );
    expect(screen.getAllByText("CONFIDENCE")).toHaveLength(2);
  });
});

/* ---------------- failures ---------------- */

describe("failures", () => {
  it("titles a network failure by its kind, never one generic message", async () => {
    mockedUnderstand.mockRejectedValue(
      new ModelApiError("Connection refused.", "network"),
    );

    render(<VoiceNyayMitraPage onBack={vi.fn()} />);
    typeAndSend("Someone threatened me and demanded money from me.");

    expect(
      await screen.findByText("The model service could not be reached:"),
    ).toBeInTheDocument();
    // Nothing rendered as a result.
    expect(screen.queryByText("CONFIDENCE")).not.toBeInTheDocument();
  });

  it("a guidance outage never costs the model result", async () => {
    mockedUnderstand.mockResolvedValue(INCIDENT_WIRE);
    mockedGuidance.mockRejectedValue(new Error("nlp down"));

    render(<VoiceNyayMitraPage onBack={vi.fn()} />);
    typeAndSend("Someone threatened me and demanded money from me.");

    expect(await screen.findByText("CONFIDENCE")).toBeInTheDocument();
    expect(
      screen.queryByText("WHAT TO DO NEXT"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("MATCHED TO A CASE STAGE"),
    ).not.toBeInTheDocument();
  });

  it("renders the guidance panel when the NLP service answers", async () => {
    mockedUnderstand.mockResolvedValue(INCIDENT_WIRE);
    mockedGuidance.mockResolvedValue(GUIDANCE);

    render(<VoiceNyayMitraPage onBack={vi.fn()} />);
    typeAndSend("Someone threatened me and demanded money from me.");

    expect(await screen.findByText("CONFIDENCE")).toBeInTheDocument();
    expect(
      screen.getByText("MATCHED TO A CASE STAGE"),
    ).toBeInTheDocument();
    expect(screen.getByText("URGENCY OF YOUR INCIDENT")).toBeInTheDocument();
  });
});

/* ---------------- voice ---------------- */

describe("voice", () => {
  it("offers the microphone without sending anything", () => {
    render(<VoiceNyayMitraPage onBack={vi.fn()} />);

    expect(screen.getByLabelText("Start voice input")).toBeInTheDocument();
    expect(mockedUnderstand).not.toHaveBeenCalled();
  });

  it("says so plainly when the browser cannot read aloud", async () => {
    // jsdom has no speech synthesis; the page must say so, not go quiet.
    expect("speechSynthesis" in window).toBe(false);

    mockedUnderstand.mockResolvedValue(INCIDENT_WIRE);
    mockedGuidance.mockRejectedValue(new Error("guidance down"));

    render(<VoiceNyayMitraPage onBack={vi.fn()} />);
    typeAndSend("Someone threatened me and demanded money from me.");

    const readButton = await screen.findByRole("button", {
      name: /read aloud/i,
    });
    fireEvent.click(readButton);

    // A message, right away — not silence.
    expect(
      await screen.findByText(/read aloud is not available/i),
    ).toBeInTheDocument();

    // Reading aloud is playback only — still exactly one turn sent.
    expect(mockedUnderstand).toHaveBeenCalledTimes(1);
  });
});

/* ---------------- language support ----------------

   The microphone and read-aloud do NOT support every language
   identically, and the page must say so rather than fail silently:

   * The ASR checkpoint (ai4bharat/indic-conformer-600m) transcribes
     हिन्दी and मराठी only — verified against its language mask. There
     is no English speech model, so choosing English shows a message
     and the account is typed instead.
   * Read-aloud covers all three, but हिन्दी/मराठी come back from the
     model in English and need one translateText call first; English
     is spoken as-is. A device with no voice for the language gets a
     message, not a wrong-accent fallback.
   ========================================================= */

type FakeUtterance = {
  text: string;
  lang: string;
  voice: SpeechSynthesisVoice | null;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
};

/* A controllable stand-in for window.speechSynthesis. `voices` is
   what getVoices() reports, so a test can simulate a device with or
   without a हिन्दी/मराठी/English voice. Every spoken utterance is
   recorded so the test can assert on language and text. */
function installSpeech(voices: SpeechSynthesisVoice[]) {
  const spoken: FakeUtterance[] = [];

  const synthesis = {
    getVoices: () => voices,
    speak: (utterance: FakeUtterance) => {
      spoken.push(utterance);
      utterance.onstart?.();
    },
    cancel: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
  };

  class FakeSpeechSynthesisUtterance {
    text: string;
    lang = "";
    voice: SpeechSynthesisVoice | null = null;
    onstart: (() => void) | null = null;
    onend: (() => void) | null = null;
    onerror: (() => void) | null = null;

    constructor(text: string) {
      this.text = text;
    }
  }

  vi.stubGlobal("speechSynthesis", synthesis);
  vi.stubGlobal("SpeechSynthesisUtterance", FakeSpeechSynthesisUtterance);

  return spoken;
}

const fakeVoice = (lang: string): SpeechSynthesisVoice =>
  ({ lang, name: `${lang} voice`, default: false, localService: true, voiceURI: `${lang}-voice` }) as SpeechSynthesisVoice;

/* jsdom has no MediaRecorder or AudioContext. Stub just enough that
   the record → WAV → transcribeVoice path runs, so the test can check
   WHICH language reaches the API. */
function installMicrophone() {
  Object.defineProperty(window.navigator, "mediaDevices", {
    value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [] }) },
    configurable: true,
  });

  vi.stubGlobal(
    "MediaRecorder",
    class {
      state = "inactive";
      mimeType = "audio/webm";
      ondataavailable: ((event: { data: Blob }) => void) | null = null;
      onstop: (() => void) | null = null;
      start() {
        this.state = "recording";
      }
      stop() {
        this.state = "inactive";
        this.ondataavailable?.({ data: new Blob(["audio"]) });
        this.onstop?.();
      }
    },
  );

  vi.stubGlobal(
    "AudioContext",
    class {
      async decodeAudioData() {
        return {
          numberOfChannels: 1,
          sampleRate: 16000,
          length: 160,
          getChannelData: () => new Float32Array(160),
        };
      }
      async close() {}
    },
  );
}

const chooseLanguage = (code: string) => {
  fireEvent.change(screen.getAllByRole("combobox")[0], {
    target: { value: code },
  });
};

/* Start recording, wait until the UI flips to "listening", then
   stop and let the recorder's async onstop/transcribe settle. */
const recordOne = async () => {
  fireEvent.click(screen.getByLabelText("Start voice input"));
  await screen.findByLabelText("Stop listening");
  fireEvent.click(screen.getByLabelText("Stop listening"));
  await waitFor(() => expect(mockedTranscribe).toHaveBeenCalled());
};

describe("microphone language support", () => {
  it("records हिन्दी and sends the हिन्दी code to the API", async () => {
    installMicrophone();
    mockedTranscribe.mockResolvedValue({
      transcribed_text: "मुझे धमकी मिली",
      language: "hi",
    });

    render(<VoiceNyayMitraPage onBack={vi.fn()} />);
    chooseLanguage("hi");
    await recordOne();

    expect(mockedTranscribe.mock.calls[0][1]).toBe("hi");
    expect(screen.getByLabelText("Start voice input")).toBeInTheDocument();
    expect(screen.queryByText(/not available/i)).not.toBeInTheDocument();
  });

  it("records मराठी and sends the मराठी code to the API", async () => {
    installMicrophone();
    mockedTranscribe.mockResolvedValue({
      transcribed_text: "मला धमकी मिळाली",
      language: "mr",
    });

    render(<VoiceNyayMitraPage onBack={vi.fn()} />);
    chooseLanguage("mr");
    await recordOne();

    expect(mockedTranscribe.mock.calls[0][1]).toBe("mr");
    expect(screen.queryByText(/not available/i)).not.toBeInTheDocument();
  });

  it("English shows a message instead of recording (no English ASR model)", () => {
    render(<VoiceNyayMitraPage onBack={vi.fn()} />);

    // English is already the default choice.
    fireEvent.click(screen.getByLabelText("Start voice input"));

    expect(mockedTranscribe).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Start voice input")).toBeInTheDocument();
    expect(
      screen.getByText(/speech input in english is not available/i),
    ).toBeInTheDocument();
  });
});

describe("read-aloud language support", () => {
  const sendTurn = async () => {
    mockedUnderstand.mockResolvedValue(INCIDENT_WIRE);
    mockedGuidance.mockRejectedValue(new Error("guidance down"));

    render(<VoiceNyayMitraPage onBack={vi.fn()} />);
    typeAndSend("Someone threatened me and demanded money from me.");
    await screen.findByText("CONFIDENCE");
    return screen.findByRole("button", { name: /read aloud/i });
  };

  it("English is spoken as-is — no translation call", async () => {
    const spoken = installSpeech([fakeVoice("en-IN")]);

    const readButton = await sendTurn();
    fireEvent.click(readButton);

    await waitFor(() => expect(spoken).toHaveLength(1));
    expect(mockedTranslate).not.toHaveBeenCalled();
    expect(spoken[0].voice?.lang).toBe("en-IN");
    expect(spoken[0].text).toMatch(/threat|category|confidence/i);
  });

  it("हिन्दी is translated first, then spoken by the हिन्दी voice", async () => {
    const spoken = installSpeech([fakeVoice("hi-IN")]);
    mockedTranslate.mockResolvedValue({
      translation_id: "t_1",
      case_id: "",
      source_text: "x",
      translated_text: "धमकी मिली",
      language: "hi",
      translated_at: "2026-10-10T00:00:00.000Z",
      glossary_matches: [],
    });

    const readButton = await sendTurn();
    chooseLanguage("hi");
    fireEvent.click(readButton);

    await waitFor(() => expect(spoken).toHaveLength(1));
    expect(mockedTranslate).toHaveBeenCalledTimes(1);
    expect(spoken[0].voice?.lang).toBe("hi-IN");
    expect(spoken[0].text).toBe("धमकी मिली");
  });

  it("मराठी with no मराठी voice shows a message instead of a wrong-accent read", async () => {
    installSpeech([fakeVoice("en-IN")]);

    const readButton = await sendTurn();
    chooseLanguage("mr");
    fireEvent.click(readButton);

    expect(
      await screen.findByText(/no मराठी voice is available/i),
    ).toBeInTheDocument();
    expect(mockedTranslate).not.toHaveBeenCalled();
  });

  it("a translation outage gets a message, never a wrong-language read", async () => {
    installSpeech([fakeVoice("mr-IN")]);
    mockedTranslate.mockRejectedValue(new Error("nlp down"));

    const readButton = await sendTurn();
    chooseLanguage("mr");
    fireEvent.click(readButton);

    expect(
      await screen.findByText(/could not be translated/i),
    ).toBeInTheDocument();
  });
});

/* ---------------- clearing ---------------- */

describe("clear conversation", () => {
  it("“Start a new account” empties the transcript without another call", async () => {
    mockedUnderstand.mockResolvedValue(INCIDENT_WIRE);
    mockedGuidance.mockRejectedValue(new Error("guidance down"));

    render(<VoiceNyayMitraPage onBack={vi.fn()} />);
    typeAndSend("Someone threatened me and demanded money from me.");
    expect(await screen.findByText("CONFIDENCE")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: /start a new account/i }),
    );

    expect(screen.queryByText("CONFIDENCE")).not.toBeInTheDocument();
    expect(screen.queryByText("What we understood")).not.toBeInTheDocument();
    expect(mockedUnderstand).toHaveBeenCalledTimes(1);
  });
});
