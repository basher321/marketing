"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { speakMessage, transcribeVoice } from "@/lib/api/orchestrator";
import type { TranscriptRead } from "@/lib/types/orchestrator";

// Voice commands and spoken replies for Command Chat (SPEC-FE-062, backend
// SPEC-BE-095). Recording uses MediaRecorder; the text comes from the
// company's own OpenAI / Groq / Gemini key; replies are read aloud in the
// language the command was spoken in.

export const MAX_RECORD_SECONDS = 90;
const BARS = 36;
const VOICE_REPLIES_KEY = "cc-voice-replies";

/** "bn" -> "Bengali" (the browser's own language names). */
export function languageLabel(code: string | null | undefined): string {
  if (!code) return "Voice";
  try {
    return new Intl.DisplayNames(["en"], { type: "language" }).of(code) ?? code;
  } catch {
    return code;
  }
}

function pickMime(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  for (const type of ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"]) {
    if (MediaRecorder.isTypeSupported(type)) return type;
  }
  return undefined;
}

export function canRecord(): boolean {
  return typeof window !== "undefined" && typeof MediaRecorder !== "undefined" && !!navigator.mediaDevices?.getUserMedia;
}

export type RecorderState = "idle" | "recording" | "transcribing" | "error";

/**
 * Microphone -> transcript. `stop()` sends the recording to the backend and
 * hands the text to `onTranscript`; `cancel()` drops it. Levels drive the
 * live waveform. Stops by itself after MAX_RECORD_SECONDS.
 */
export function useVoiceRecorder(onTranscript: (t: TranscriptRead) => void) {
  const [state, setState] = useState<RecorderState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [levels, setLevels] = useState<number[]>(() => Array(BARS).fill(0.05));
  const [elapsed, setElapsed] = useState(0);
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const chunks = useRef<Blob[]>([]);
  const audioCtx = useRef<AudioContext | null>(null);
  const frame = useRef<number | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const keep = useRef(true); // false = cancel: discard the recording
  const onText = useRef(onTranscript);
  onText.current = onTranscript;

  const cleanup = useCallback(() => {
    if (frame.current !== null) cancelAnimationFrame(frame.current);
    if (timer.current !== null) clearInterval(timer.current);
    frame.current = null;
    timer.current = null;
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
    void audioCtx.current?.close().catch(() => undefined);
    audioCtx.current = null;
    setLevels(Array(BARS).fill(0.05));
  }, []);

  useEffect(() => () => {
    keep.current = false;
    if (recorder.current?.state === "recording") recorder.current.stop();
    cleanup();
  }, [cleanup]);

  const finish = useCallback(
    async (blob: Blob) => {
      setState("transcribing");
      try {
        const t = await transcribeVoice(blob);
        setState("idle");
        onText.current(t);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        setState("error");
      }
    },
    [],
  );

  const start = useCallback(async () => {
    setError(null);
    if (!canRecord()) {
      setError("Voice commands need a browser with microphone recording (Chrome, Edge, Firefox or Safari).");
      setState("error");
      return;
    }
    let media: MediaStream;
    try {
      media = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch {
      setError("Allow the microphone in your browser to use voice commands.");
      setState("error");
      return;
    }
    stream.current = media;
    const mime = pickMime();
    const rec = new MediaRecorder(media, { ...(mime ? { mimeType: mime } : {}), audioBitsPerSecond: 32_000 });
    chunks.current = [];
    keep.current = true;
    rec.ondataavailable = (e) => {
      if (e.data.size) chunks.current.push(e.data);
    };
    rec.onstop = () => {
      const blob = new Blob(chunks.current, { type: rec.mimeType || mime || "audio/webm" });
      cleanup();
      if (!keep.current) {
        setState("idle");
        return;
      }
      if (blob.size < 1000) {
        setError("That was too short. Hold on a moment longer while you speak.");
        setState("error");
        return;
      }
      void finish(blob);
    };
    recorder.current = rec;
    rec.start(250);
    setElapsed(0);
    setState("recording");

    // Live waveform from the microphone level.
    try {
      const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const ctx = new Ctx();
      audioCtx.current = ctx;
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      ctx.createMediaStreamSource(media).connect(analyser);
      const data = new Uint8Array(analyser.fftSize);
      const tick = () => {
        analyser.getByteTimeDomainData(data);
        let sum = 0;
        for (const v of data) sum += ((v - 128) / 128) ** 2;
        const level = Math.min(1, Math.sqrt(sum / data.length) * 4);
        setLevels((prev) => [...prev.slice(1), Math.max(0.05, level)]);
        frame.current = requestAnimationFrame(tick);
      };
      tick();
    } catch {
      // No Web Audio: the bars stay flat; recording still works.
    }
    const began = Date.now();
    timer.current = setInterval(() => {
      const s = Math.floor((Date.now() - began) / 1000);
      setElapsed(s);
      if (s >= MAX_RECORD_SECONDS && recorder.current?.state === "recording") recorder.current.stop();
    }, 250);
  }, [cleanup, finish]);

  const stop = useCallback(() => {
    keep.current = true;
    if (recorder.current?.state === "recording") recorder.current.stop();
  }, []);

  const cancel = useCallback(() => {
    keep.current = false;
    if (recorder.current?.state === "recording") recorder.current.stop();
    else cleanup();
    setError(null);
    setState("idle");
  }, [cleanup]);

  const dismiss = useCallback(() => {
    setError(null);
    setState("idle");
  }, []);

  return { state, error, levels, elapsed, start, stop, cancel, dismiss };
}

export function MicIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
    </svg>
  );
}

function clock(s: number): string {
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** The composer while recording / transcribing / showing a voice error. */
export function VoiceBar({ rec }: { rec: ReturnType<typeof useVoiceRecorder> }) {
  const { state, levels, elapsed, stop, cancel, start, dismiss, error } = rec;
  useEffect(() => {
    if (state !== "recording") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        cancel();
      } else if (e.key === " " && !(e.target instanceof HTMLTextAreaElement) && !(e.target instanceof HTMLInputElement)) {
        e.preventDefault();
        stop();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [state, stop, cancel]);

  if (state === "error") {
    return (
      <div className="cc-voicebar" role="alert">
        <span className="min-w-0 flex-1 text-[12.5px] text-danger">{error}</span>
        <button type="button" className="btn btn-secondary btn-sm" onClick={dismiss}>
          Close
        </button>
        <button type="button" className="btn btn-sm" onClick={() => void start()}>
          Try again
        </button>
      </div>
    );
  }
  if (state === "transcribing") {
    return (
      <div className="cc-voicebar" aria-live="polite">
        <span className="cc-dots" aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
        <span className="flex-1 text-[12.5px] text-muted">Transcribing your voice…</span>
      </div>
    );
  }
  return (
    <div className="cc-voicebar" aria-live="polite">
      <span className="cc-rec-dot" aria-hidden="true" />
      <span className="w-[38px] text-xs tabular-nums text-muted">{clock(elapsed)}</span>
      <div className="cc-wave" aria-label="Recording level">
        {levels.map((l, i) => (
          <span key={i} style={{ height: `${Math.round(6 + l * 28)}px` }} />
        ))}
      </div>
      <span className="hidden text-[11px] text-muted sm:inline">
        {MAX_RECORD_SECONDS - elapsed <= 10 ? `${MAX_RECORD_SECONDS - elapsed}s left` : "Space to stop · Esc to cancel"}
      </span>
      <button type="button" className="btn btn-secondary btn-sm" onClick={cancel}>
        Cancel
      </button>
      <button type="button" className="cc-icon-btn rec" onClick={stop} aria-label="Stop recording" title="Stop recording">
        <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true">
          <rect x="5" y="5" width="14" height="14" rx="3" fill="currentColor" />
        </svg>
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Spoken replies
// ---------------------------------------------------------------------------

export type PlayState = "loading" | "playing" | "paused" | "blocked" | "error" | "done";
export interface ReplyAudio {
  state: PlayState;
  caption: string | null;
  note: string | null;
  error: string | null;
}

/** "Voice replies" on/off, remembered per browser (guarded localStorage). */
export function useVoiceRepliesSetting(): [boolean, (on: boolean) => void] {
  const [on, setOn] = useState(true);
  useEffect(() => {
    try {
      const v = localStorage.getItem(VOICE_REPLIES_KEY);
      if (v !== null) setOn(v === "1");
    } catch {
      // storage blocked: keep the default
    }
  }, []);
  const set = useCallback((next: boolean) => {
    setOn(next);
    try {
      localStorage.setItem(VOICE_REPLIES_KEY, next ? "1" : "0");
    } catch {
      // storage blocked: the choice lasts for this page only
    }
  }, []);
  return [on, set];
}

function base64Blob(data: string, mime: string): Blob {
  const bin = atob(data);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes], { type: mime });
}

/**
 * One reply plays at a time. `enqueue(id, language)` (auto-play after a voice
 * command) waits its turn, so the reply and its later summary both play, in
 * order; its audio is fetched right away so there's no gap. `toggle` (the
 * Listen button) interrupts. Audio is fetched once per message + language and
 * kept as an object URL until the page closes.
 */
export function useReplyPlayer() {
  const [replies, setReplies] = useState<Record<string, ReplyAudio>>({});
  const [current, setCurrent] = useState<string | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const urls = useRef<Map<string, string>>(new Map());
  const fetching = useRef<Map<string, Promise<string>>>(new Map());
  const queue = useRef<{ id: string; language: string | null }[]>([]);
  const pending = useRef<string | null>(null); // fetching, about to play
  const playing = useRef<string | null>(null);

  const patch = useCallback((id: string, p: Partial<ReplyAudio>) => {
    const blank: ReplyAudio = { state: "loading", caption: null, note: null, error: null };
    setReplies((r) => ({ ...r, [id]: { ...blank, ...r[id], ...p } }));
  }, []);

  useEffect(() => {
    const map = urls.current;
    return () => {
      audio.current?.pause();
      map.forEach((u) => URL.revokeObjectURL(u));
      map.clear();
    };
  }, []);

  // The audio URL for a message in a language: cached, in flight, or fetched now.
  const audioUrl = useCallback(
    (id: string, language: string | null): Promise<string> => {
      const key = `${id}:${language ?? ""}`;
      const cached = urls.current.get(key);
      if (cached) return Promise.resolve(cached);
      const inFlight = fetching.current.get(key);
      if (inFlight) return inFlight;
      const job = speakMessage(id, language).then((res) => {
        const url = URL.createObjectURL(base64Blob(res.audio, res.mime));
        urls.current.set(key, url);
        setReplies((r) => ({
          ...r,
          [id]: { ...{ state: "paused" as PlayState, error: null }, ...r[id], caption: res.text, note: res.note },
        }));
        return url;
      });
      fetching.current.set(key, job);
      void job.catch(() => undefined).finally(() => fetching.current.delete(key));
      return job;
    },
    [],
  );

  const play = useRef<(id: string, language: string | null) => Promise<void>>(async () => undefined);
  const playNext = useCallback(() => {
    const next = queue.current.shift();
    if (next) void play.current(next.id, next.language);
  }, []);

  const start = useCallback(
    (id: string, url: string) => {
      audio.current?.pause();
      const el = new Audio(url);
      audio.current = el;
      pending.current = null;
      playing.current = id;
      setCurrent(id);
      el.onended = () => {
        patch(id, { state: "done" });
        playing.current = null;
        setCurrent((c) => (c === id ? null : c));
        playNext();
      };
      el.play().then(
        () => patch(id, { state: "playing" }),
        (err: unknown) => {
          playing.current = null;
          setCurrent((c) => (c === id ? null : c));
          // Autoplay blocked: the user taps once to hear it (the queue waits).
          if (err instanceof DOMException && err.name === "NotAllowedError") {
            patch(id, { state: "blocked" });
            return;
          }
          patch(id, { state: "error", error: "This browser couldn't play the audio." });
          playNext();
        },
      );
    },
    [patch, playNext],
  );

  play.current = async (id: string, language: string | null) => {
    audio.current?.pause();
    if (playing.current && playing.current !== id) patch(playing.current, { state: "paused" });
    playing.current = null;
    pending.current = id;
    if (!urls.current.has(`${id}:${language ?? ""}`)) patch(id, { state: "loading", error: null });
    try {
      const url = await audioUrl(id, language);
      if (pending.current !== id) return; // something else started meanwhile
      start(id, url);
    } catch (err) {
      if (pending.current === id) pending.current = null;
      patch(id, { state: "error", error: err instanceof Error ? err.message : String(err) });
      playNext();
    }
  };

  /** Auto-play: waits for whatever is loading or playing. */
  const enqueue = useCallback(
    (id: string, language: string | null) => {
      void audioUrl(id, language).catch(() => undefined); // fetch now, play in turn
      if (pending.current === null && playing.current === null) void play.current(id, language);
      else queue.current.push({ id, language });
    },
    [audioUrl],
  );

  const stopAll = useCallback(() => {
    queue.current = [];
    pending.current = null;
    if (audio.current) {
      audio.current.pause();
      audio.current = null;
    }
    if (playing.current) patch(playing.current, { state: "paused" });
    playing.current = null;
    setCurrent(null);
  }, [patch]);

  /** The Listen button: pause/resume this one, or interrupt and play it now. */
  const toggle = useCallback(
    (id: string, language: string | null) => {
      const r = replies[id];
      if (playing.current === id && r?.state === "playing") {
        audio.current?.pause();
        patch(id, { state: "paused" });
        return;
      }
      if (playing.current === id && audio.current && r?.state === "paused") {
        void audio.current.play().then(() => patch(id, { state: "playing" }));
        return;
      }
      if (r?.state !== "blocked") queue.current = [];
      void play.current(id, language);
    },
    [replies, patch],
  );

  return { replies, current, enqueue, toggle, stopAll };
}

/** Listen button + live state + spoken caption under an AI bubble. */
export function ReplyVoice({
  audio,
  shownText,
  onToggle,
}: {
  audio: ReplyAudio | undefined;
  shownText: string;
  onToggle: () => void;
}) {
  const state = audio?.state;
  // The caption shows only when the spoken text isn't the shown text (a translation).
  const norm = (s: string) => s.replace(/[^\p{L}\p{N}]/gu, "").toLowerCase().slice(0, 40);
  const showCaption = !!audio?.caption && !norm(shownText).startsWith(norm(audio.caption));
  return (
    <>
      {state === "blocked" ? (
        <button type="button" className="btn btn-sm" onClick={onToggle}>
          🔊 Tap to hear the reply
        </button>
      ) : (
        <button type="button" className="cc-link" onClick={onToggle} disabled={state === "loading"} aria-label={state === "playing" ? "Pause" : "Listen"}>
          {state === "loading" ? (
            <>
              <span className="cc-dots" aria-hidden="true">
                <span />
                <span />
                <span />
              </span>
              Preparing voice…
            </>
          ) : state === "playing" ? (
            <>
              <span className="cc-speaking" aria-hidden="true">
                <span />
                <span />
                <span />
                <span />
              </span>
              Pause
            </>
          ) : (
            <>🔊 Listen</>
          )}
        </button>
      )}
      {state === "error" && audio?.error && <span className="basis-full text-[11.5px] text-danger">{audio.error}</span>}
      {audio?.note && <span className="basis-full text-[11.5px] text-muted">{audio.note}</span>}
      {showCaption && (
        <div className="cc-caption basis-full">
          <span className="mr-1 text-[11px] text-muted">Spoken:</span>
          {audio?.caption}
        </div>
      )}
    </>
  );
}
