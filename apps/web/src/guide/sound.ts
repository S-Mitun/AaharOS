/**
 * The app-wide sound switch in the top bar. Off: nothing plays and the tour does not read itself aloud. It is the
 * same setting as the tour's "Read each step aloud" box, so the two always agree.
 */
const KEY = "aaharos.voice.auto";
const EVENT = "aaharos:sound";

export function soundOn(): boolean {
  try {
    return window.localStorage.getItem(KEY) !== "0";
  } catch {
    return true;
  }
}

export function setSound(on: boolean): void {
  try {
    window.localStorage.setItem(KEY, on ? "1" : "0");
  } catch {
    /* storage blocked */
  }
  window.dispatchEvent(new CustomEvent(EVENT, { detail: on }));
}

export function onSoundChange(handler: (on: boolean) => void): () => void {
  const listener = (e: Event) => handler((e as CustomEvent<boolean>).detail);
  window.addEventListener(EVENT, listener);
  return () => window.removeEventListener(EVENT, listener);
}
