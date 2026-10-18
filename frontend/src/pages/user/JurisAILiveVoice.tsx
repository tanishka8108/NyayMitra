import { useEffect, useRef, useState } from "react";
import { Mic, PhoneOff, Radio, X } from "lucide-react";
import {
  TRANSLATION_API_BASE_URL,
  TRANSLATION_API_KEY,
} from "../../api/config";
import type { WhatHappenedLanguage } from "../../api/whatHappenedApi";

type Props = {
  language: WhatHappenedLanguage;
  onClose: () => void;
};

type LiveEvent = {
  type: string;
  message?: string;
  text?: string;
  data?: string;
  mime_type?: string;
};

function pcm16ToBase64(input: Float32Array, sampleRate: number): string {
  const ratio = sampleRate / 16000;
  const outputLength = Math.floor(input.length / ratio);
  const pcm = new Int16Array(outputLength);

  for (let i = 0; i < outputLength; i++) {
    const start = Math.floor(i * ratio);
    const end = Math.min(input.length, Math.floor((i + 1) * ratio));
    let sum = 0;
    for (let j = start; j < end; j++) sum += input[j];
    const sample = end > start ? sum / (end - start) : 0;
    pcm[i] = Math.max(-1, Math.min(1, sample)) * (sample < 0 ? 32768 : 32767);
  }

  const bytes = new Uint8Array(pcm.buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

export default function JurisAILiveVoice({ language, onClose }: Props) {
  const [status, setStatus] = useState("Ready to connect");
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState("");
  const [captions, setCaptions] = useState<string[]>([]);

  const socketRef = useRef<WebSocket | null>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const playbackTimeRef = useRef(0);
  const playbackSourcesRef = useRef(new Set<AudioBufferSourceNode>());
  const stoppingRef = useRef(false);

  const stopPlayback = () => {
    for (const source of playbackSourcesRef.current) {
      try {
        source.stop();
      } catch {
        // The audio source may already have ended.
      }
    }
    playbackSourcesRef.current.clear();
    playbackTimeRef.current = 0;
  };

  const cleanup = async (sendEnd: boolean) => {
    stoppingRef.current = true;

    const socket = socketRef.current;
    if (sendEnd && socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "end" }));
    }
    socketRef.current = null;

    if (socket && socket.readyState < WebSocket.CLOSING) {
      socket.close();
    }

    if (processorRef.current) {
      processorRef.current.onaudioprocess = null;
      processorRef.current.disconnect();
      processorRef.current = null;
    }

    sourceRef.current?.disconnect();
    sourceRef.current = null;

    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;

    stopPlayback();

    const context = contextRef.current;
    contextRef.current = null;
    if (context && context.state !== "closed") {
      await context.close().catch(() => undefined);
    }

    setConnected(false);
    setStatus("Disconnected");
  };

  const startVoice = async () => {
    if (connected || socketRef.current) return;

    setError("");
    setCaptions([]);
    setStatus("Requesting microphone…");
    stoppingRef.current = false;

    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error("Microphone access is unavailable in this browser.");
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;

      const context = new AudioContext();
      contextRef.current = context;
      await context.resume();

      const wsBase = TRANSLATION_API_BASE_URL.replace(
        /^https:/,
        "wss:",
      ).replace(/^http:/, "ws:");

      const socket = new WebSocket(`${wsBase}/api/juris-ai/live`);
      socketRef.current = socket;

      socket.onopen = () => {
        socket.send(
          JSON.stringify({
            type: "auth",
            token: TRANSLATION_API_KEY,
            language,
          }),
        );
      };

      socket.onmessage = (message: MessageEvent<string>) => {
        let event: LiveEvent;
        try {
          event = JSON.parse(message.data) as LiveEvent;
        } catch {
          return;
        }

        if (event.type === "connected") {
          setConnected(true);
          setStatus("Listening");
          const source = context.createMediaStreamSource(stream);
          const processor = context.createScriptProcessor(4096, 1, 1);

          processor.onaudioprocess = (audioEvent) => {
            if (socket.readyState !== WebSocket.OPEN) return;
            const input = audioEvent.inputBuffer.getChannelData(0);
            const encoded = pcm16ToBase64(
              input,
              audioEvent.inputBuffer.sampleRate,
            );
            if (encoded) {
              socket.send(JSON.stringify({ type: "audio", data: encoded }));
            }
            // Prevent microphone audio from playing through the speakers.
            audioEvent.outputBuffer.getChannelData(0).fill(0);
          };

          source.connect(processor);
          processor.connect(context.destination);
          sourceRef.current = source;
          processorRef.current = processor;
          return;
        }

        if (event.type === "input_transcript" && event.text) {
          setCaptions((current) => [
            ...current.slice(-7),
            `You: ${event.text}`,
          ]);
          return;
        }

        if (event.type === "output_transcript" && event.text) {
          setCaptions((current) => [
            ...current.slice(-7),
            `Juris AI: ${event.text}`,
          ]);
          setStatus("Speaking");
          return;
        }

        if (event.type === "audio" && event.data) {
          const bytes = Uint8Array.from(atob(event.data), (character) =>
            character.charCodeAt(0),
          );
          const usableLength = bytes.byteLength - (bytes.byteLength % 2);
          if (!usableLength) return;

          const pcm = new Int16Array(
            bytes.buffer,
            bytes.byteOffset,
            usableLength / 2,
          );
          const sampleRate = Number(
            event.mime_type?.match(/rate=(\d+)/)?.[1] ?? 24000,
          );
          const buffer = context.createBuffer(1, pcm.length, sampleRate);
          const channel = buffer.getChannelData(0);

          for (let i = 0; i < pcm.length; i++) {
            channel[i] = pcm[i] / (pcm[i] < 0 ? 32768 : 32767);
          }

          const source = context.createBufferSource();
          source.buffer = buffer;
          source.connect(context.destination);

          const startAt = Math.max(
            context.currentTime,
            playbackTimeRef.current,
          );
          source.start(startAt);
          playbackTimeRef.current = startAt + buffer.duration;
          playbackSourcesRef.current.add(source);
          source.onended = () => playbackSourcesRef.current.delete(source);
          setStatus("Speaking");
          return;
        }

        if (event.type === "interrupted") {
          stopPlayback();
          setStatus("Listening");
          return;
        }

        if (event.type === "turn_complete") {
          setStatus("Listening");
          return;
        }

        if (event.type === "error") {
          setError(event.message || "Live voice encountered an error.");
          setStatus("Connection error");
        }
      };

      socket.onerror = () => {
        setError(
          "Could not connect to live voice. Check that the NLP service is running.",
        );
      };

      socket.onclose = () => {
        if (!stoppingRef.current) {
          setConnected(false);
          setStatus("Disconnected");
        }
      };
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Unable to start live voice.",
      );
      await cleanup(false);
    }
  };

  const endVoice = async () => {
    await cleanup(true);
  };

  useEffect(() => {
    return () => {
      void cleanup(true);
    };
    // This cleanup is for unmounting the live-voice panel.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    const t = window.setTimeout(() => {
      document
        .querySelector(".juris-live")
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 50);
    return () => window.clearTimeout(t);
  }, []);
  return (
    <section className="juris-live" aria-label="Juris AI live voice">
      <header className="juris-live-header">
        <div className="juris-live-title">
          <Radio size={19} />
          <div>
            <strong>Juris AI · Live Voice</strong>
            <span>{status}</span>
          </div>
        </div>
        <button type="button" onClick={onClose} aria-label="Close live voice">
          <X size={18} />
        </button>
      </header>

      <div className={`juris-live-orb ${connected ? "is-active" : ""}`}>
        <Mic size={30} />
      </div>

      <p className="juris-live-hint">
        Speak naturally in{" "}
        {language === "hi"
          ? "Hindi"
          : language === "mr"
            ? "Marathi"
            : "English"}
        . You can interrupt the assistant by speaking.
      </p>

      <div className="juris-live-captions" aria-live="polite">
        {captions.length ? (
          captions.map((caption, index) => (
            <p key={`${index}-${caption}`}>{caption}</p>
          ))
        ) : (
          <p>Your conversation captions will appear here.</p>
        )}
      </div>

      {error && (
        <p className="juris-live-error" role="alert">
          {error}
        </p>
      )}

      <div className="juris-live-controls">
        {!connected ? (
          <button
            type="button"
            className="juris-live-start"
            onClick={() => void startVoice()}
          >
            <Mic size={17} /> Start conversation
          </button>
        ) : (
          <button
            type="button"
            className="juris-live-end"
            onClick={() => void endVoice()}
          >
            <PhoneOff size={17} /> End conversation
          </button>
        )}
      </div>
      <p className="juris-live-note">
        General information only. For verified legal analysis and court-order
        explanations, use the Juris AI text chat.
      </p>
    </section>
  );
}
