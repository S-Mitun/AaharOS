import { useEffect, useRef, useState } from "react";
import { useT } from "../lib/i18n";

/**
 * 🔊 Listen: plays a recorded voice track (/voice/{en|ta}/{track}.mp3) in the language on screen. If the language is
 * changed while it plays, it carries on in the other language at once.
 */
export function ListenButton({ track, label }: { track: string; label?: string }) {
  const { t, lang } = useT();
  const [playing, setPlaying] = useState(false);
  const audio = useRef<HTMLAudioElement | null>(null);

  const stop = () => {
    audio.current?.pause();
    audio.current = null;
    setPlaying(false);
  };

  const play = (l: string) => {
    audio.current?.pause();
    const a = new Audio(`/voice/${l}/${track}.mp3`);
    audio.current = a;
    a.onended = () => {
      if (audio.current === a) setPlaying(false);
    };
    setPlaying(true);
    a.play().catch(() => setPlaying(false));
  };

  // a new language while playing: continue in that language
  const playingRef = useRef(false);
  playingRef.current = playing;
  useEffect(() => {
    if (playingRef.current) play(lang);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only a language change restarts the voice
  }, [lang]);
  useEffect(() => () => audio.current?.pause(), []);

  return playing ? (
    <button type="button" className="btn listen-btn" onClick={stop}>
      <span aria-hidden="true">■</span> {t("Stop")}
    </button>
  ) : (
    <button type="button" className="btn btn-primary listen-btn" onClick={() => play(lang)}>
      <span aria-hidden="true">🔊</span> {label ?? t("Listen")}
    </button>
  );
}
