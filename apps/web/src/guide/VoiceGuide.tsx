import { useCallback, useEffect, useRef, useState } from "react";
import { useT } from "../lib/i18n";

/**
 * The voice guide for the tour: plays the recorded voice of the current step in the chosen language (a natural Tamil
 * or Indian-English voice, recorded from the step card's own text, so it works on every device). When Tamil is
 * chosen it switches to Tamil at once. If a recording cannot be played it falls back to the browser's own speech.
 * "Read each step aloud" keeps it reading as you move through the tour.
 */
const AUTO_KEY = "aaharos.voice.auto";
const synth = (): SpeechSynthesis | null =>
  typeof window !== "undefined" && "speechSynthesis" in window ? window.speechSynthesis : null;

function pickVoice(lang: "en" | "ta"): SpeechSynthesisVoice | null {
  const voices = synth()?.getVoices() ?? [];
  if (lang === "ta") return voices.find((v) => v.lang.toLowerCase().startsWith("ta")) ?? null;
  return (
    voices.find((v) => v.lang === "en-IN") ??
    voices.find((v) => v.lang.toLowerCase().startsWith("en-gb")) ??
    voices.find((v) => v.lang.toLowerCase().startsWith("en")) ??
    null
  );
}

/** The card's text in reading order: title, who, where, what to do, what you should see, why. */
function cardScript(card: Element): string[] {
  const parts: string[] = [];
  const clean = (s: string | null | undefined) =>
    (s ?? "")
      .replace(/[ⓘ✓▲▼⏳]/g, "")
      .replace(/→/g, ", ")
      .replace(/\s+/g, " ")
      .trim();
  const title = clean(card.querySelector("h2")?.textContent);
  if (title) parts.push(title + ".");
  card.querySelectorAll(".step-meta > div").forEach((row) => {
    const label = clean(row.querySelector(".meta-label")?.textContent);
    const copy = row.cloneNode(true) as Element;
    copy.querySelector(".meta-label")?.remove();
    copy.querySelector("a")?.remove();
    const value = clean(copy.textContent);
    if (value) parts.push(`${label}: ${value}.`);
  });
  card.querySelectorAll("section").forEach((sec) => {
    const heading = clean(sec.querySelector("h3")?.textContent);
    if (heading) parts.push(heading + ".");
    sec.querySelectorAll("li, p, dt, dd").forEach((el) => {
      if (el.closest("li") && el.tagName !== "LI") return;
      const line = clean(el.textContent);
      if (line) parts.push(line);
    });
  });
  // speak sentence by sentence: long utterances stop early in some browsers
  return parts.flatMap((p) => p.split(/(?<=[.!?।])\s+/)).filter(Boolean);
}

export function VoiceGuide({ stepId }: { stepId: string }) {
  const { t, lang } = useT();
  const supported = typeof Audio !== "undefined" || !!synth();
  const [speaking, setSpeaking] = useState(false);
  const [paused, setPaused] = useState(false);
  const [auto, setAuto] = useState(() => {
    try {
      return window.localStorage.getItem(AUTO_KEY) === "1";
    } catch {
      return false;
    }
  });
  const [noTamilVoice, setNoTamilVoice] = useState(false);
  const run = useRef(0);
  const audio = useRef<HTMLAudioElement | null>(null);

  const stop = useCallback(() => {
    run.current += 1;
    audio.current?.pause();
    audio.current = null;
    synth()?.cancel();
    setSpeaking(false);
    setPaused(false);
  }, []);

  /** The browser's own speech, from the card's text: used only when the recording cannot be played. */
  const speakFromText = useCallback(() => {
    const s = synth();
    const card = document.querySelector(".step-card");
    if (!s || !card) return;
    s.cancel();
    const mine = ++run.current;
    const voice = pickVoice(lang);
    setNoTamilVoice(lang === "ta" && !voice);
    const lines = cardScript(card);
    setSpeaking(true);
    setPaused(false);
    lines.forEach((line: string, i: number) => {
      const u = new SpeechSynthesisUtterance(line);
      u.lang = lang === "ta" ? "ta-IN" : "en-IN";
      if (voice) u.voice = voice;
      u.rate = 1;
      if (i === lines.length - 1)
        u.onend = () => {
          if (run.current === mine) setSpeaking(false);
        };
      s.speak(u);
    });
  }, [lang]);

  /** The recorded voice for this step and language (natural Tamil or Indian-English voice, on every device). */
  const speak = useCallback(() => {
    stop();
    const mine = run.current;
    setNoTamilVoice(false);
    const a = new Audio(`/voice/${lang}/${stepId}.mp3`);
    audio.current = a;
    a.onended = () => {
      if (run.current === mine) setSpeaking(false);
    };
    a.onerror = () => {
      if (run.current === mine) speakFromText();
    };
    setSpeaking(true);
    setPaused(false);
    a.play().catch(() => {
      if (run.current === mine) speakFromText();
    });
  }, [lang, stepId, stop, speakFromText]);

  // A new step, or a new language: read again if the voice was on (the card is translated a moment later).
  const wasSpeaking = useRef(false);
  wasSpeaking.current = speaking;
  useEffect(() => {
    if (!supported) return;
    if (!auto && !wasSpeaking.current) return;
    const timer = window.setTimeout(speak, 450);
    return () => window.clearTimeout(timer);
  }, [stepId, lang, auto, supported, speak]);

  // Voices load late in Chrome; stop speaking when the tour is left.
  useEffect(() => {
    const s = synth();
    if (!s) return;
    const loaded = () => undefined;
    s.addEventListener?.("voiceschanged", loaded);
    return () => {
      s.removeEventListener?.("voiceschanged", loaded);
      s.cancel();
    };
  }, []);
  useEffect(() => () => audio.current?.pause(), []);

  if (!supported)
    return <p className="muted small">{t("Voice is not available in this browser.")}</p>;

  return (
    <div className="voice-guide" role="group" aria-label={t("Voice guide")}>
      <span className="voice-label" aria-hidden="true">
        🔊
      </span>
      {!speaking ? (
        <button type="button" className="btn btn-primary" onClick={speak}>
          {t("Listen to this step")}
        </button>
      ) : paused ? (
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => {
            if (audio.current) void audio.current.play();
            else synth()?.resume();
            setPaused(false);
          }}
        >
          {t("Resume")}
        </button>
      ) : (
        <button
          type="button"
          className="btn"
          onClick={() => {
            if (audio.current) audio.current.pause();
            else synth()?.pause();
            setPaused(true);
          }}
        >
          {t("Pause")}
        </button>
      )}
      {speaking && (
        <button type="button" className="btn btn-ghost" onClick={stop}>
          {t("Stop")}
        </button>
      )}
      <label className="voice-auto">
        <input
          type="checkbox"
          checked={auto}
          onChange={(e) => {
            setAuto(e.target.checked);
            try {
              window.localStorage.setItem(AUTO_KEY, e.target.checked ? "1" : "0");
            } catch {
              /* storage blocked */
            }
            if (!e.target.checked) stop();
          }}
        />{" "}
        {t("Read each step aloud")}
      </label>
      {speaking && !paused && (
        <span className="muted small" aria-live="polite">
          {t("Speaking…")}
        </span>
      )}
      {noTamilVoice && (
        <p className="muted small voice-note">
          {t(
            "This device has no Tamil voice installed, so the reading may sound wrong. Microsoft Edge has one built in; on Windows you can also add Tamil speech in Settings → Time & language → Speech.",
          )}
        </p>
      )}
    </div>
  );
}
