const LAST_STEP_KEY = "aaharos.guide.lastStep";

/** Remember the last tour step the visitor saw. Storage can be blocked; the guide still works without it. */
export function rememberStep(id: string): void {
  try {
    window.localStorage.setItem(LAST_STEP_KEY, id);
  } catch {
    /* private mode or blocked storage */
  }
}

export function recalledStep(): string | null {
  try {
    return window.localStorage.getItem(LAST_STEP_KEY);
  } catch {
    return null;
  }
}
