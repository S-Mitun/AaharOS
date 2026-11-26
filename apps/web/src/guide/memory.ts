import { STEPS } from "./steps";

const LAST_STEP_KEY = "aaharos.guide.lastStep";
const VISITED_KEY = "aaharos.guide.visited";
const DONE_KEY = "aaharos.guide.completed";

/** Storage can be blocked (private mode); the guide still works without it, and the gate then stays closed. */
function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* private mode or blocked storage */
  }
}

/** Remember the last tour step the visitor saw, and that they saw it. */
export function rememberStep(id: string): void {
  write(LAST_STEP_KEY, id);
  const seen = new Set(visitedSteps());
  seen.add(id);
  write(VISITED_KEY, JSON.stringify([...seen]));
}

export function recalledStep(): string | null {
  return read(LAST_STEP_KEY);
}

export function visitedSteps(): string[] {
  try {
    const raw: unknown = JSON.parse(read(VISITED_KEY) ?? "[]");
    return Array.isArray(raw) ? raw.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

/** Steps of the tour not seen yet in this round (the tour is finished only when every step was opened). */
export function stepsLeft(): string[] {
  const seen = new Set(visitedSteps());
  return STEPS.filter((s) => !seen.has(s.id)).map((s) => s.id);
}

/** The guided tour is the mandatory first task: own accounts open only once it has been finished on this device. */
export function tourCompleted(): boolean {
  return read(DONE_KEY) === "yes";
}

export function markTourCompleted(): void {
  write(DONE_KEY, "yes");
}

/** Start the tour again from step 1 (any number of times). Finishing it once keeps own accounts open. */
export function restartTour(): void {
  write(VISITED_KEY, "[]");
  write(LAST_STEP_KEY, STEPS[0]!.id);
}

export const DEMO_EMAIL_DOMAIN = "@aaharos-demo.invalid";
