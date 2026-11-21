import type { OutboxEntry, SendResult } from "./types";

/**
 * The outbox sync engine (MP08, G5), written as a pure state machine with an injected clock, network and store so
 * tests can drive backoff, acknowledgements, conflicts and 401s.
 *
 * - Network errors, 5xx, 408 and 429 keep the order "Saved on phone" and retry with exponential backoff
 *   (2 s doubling to 5 min, with jitter).
 * - Any other 4xx moves it to "Needs attention" with the server's reason (the conflict view).
 * - 401 pauses sync until the salesman signs in again; the outbox is kept.
 * - "Received by factory" is set only from the server's 201/200 carrying an order number.
 */

export const BASE_DELAY_MS = 2_000;
export const MAX_DELAY_MS = 5 * 60_000;

/** Delay before retry number `attempts` (1, 2, …): 2 s, 4 s, 8 s … capped at 5 min, times a jitter of 0.8–1.2. */
export function backoffMs(attempts: number, random: number): number {
  const exp = Math.min(MAX_DELAY_MS, BASE_DELAY_MS * 2 ** Math.max(0, attempts - 1));
  const jittered = Math.round(exp * (0.8 + 0.4 * random));
  return Math.min(MAX_DELAY_MS, Math.max(BASE_DELAY_MS * 0.8, jittered));
}

export function isRetryable(result: SendResult): boolean {
  if (result.kind === "network") return true;
  if (result.kind === "ok") return false;
  return result.status >= 500 || result.status === 408 || result.status === 429;
}

export interface Applied {
  entry: OutboxEntry;
  /** True after a 401: stop sending until the user signs in again. */
  pause: boolean;
}

/** The next state of one entry after one send attempt. Pure. */
export function applyResult(
  entry: OutboxEntry,
  result: SendResult,
  now: number,
  random: number,
): Applied {
  if (result.kind === "ok" && result.order.order_no) {
    const rest: OutboxEntry = { ...entry };
    delete rest.lastError;
    return {
      entry: {
        ...rest,
        state: "received",
        serverOrder: {
          id: result.order.id,
          orderNo: result.order.order_no,
          status: result.order.status,
          stale: result.order.stale,
        },
      },
      pause: false,
    };
  }
  if (result.kind === "http" && result.status === 401) {
    return {
      entry: {
        ...entry,
        state: "saved",
        lastError: { status: 401, code: result.code, message: "Sign in again to send this order." },
      },
      pause: true,
    };
  }
  if (isRetryable(result) || result.kind === "ok") {
    const attempts = entry.attempts + 1;
    return {
      entry: {
        ...entry,
        state: "saved",
        attempts,
        nextAttemptAt: now + backoffMs(attempts, random),
        lastError:
          result.kind === "http"
            ? { status: result.status, code: result.code, message: result.message }
            : { status: 0, code: "offline", message: "No connection. It will send by itself." },
      },
      pause: false,
    };
  }
  const refused =
    result.kind === "http"
      ? { status: result.status, code: result.code, message: result.message }
      : { status: 0, code: "unknown", message: "The factory could not take this order." };
  return { entry: { ...entry, state: "attention", lastError: refused }, pause: false };
}

/** Orders waiting to go, oldest first. */
export function dueEntries(entries: OutboxEntry[], now: number): OutboxEntry[] {
  return entries
    .filter((e) => e.state === "saved" && e.nextAttemptAt <= now)
    .sort((a, b) => a.capturedAt.localeCompare(b.capturedAt));
}

/** Milliseconds until the next saved order is due, or null if none is waiting. */
export function msUntilNext(entries: OutboxEntry[], now: number): number | null {
  const waiting = entries.filter((e) => e.state === "saved").map((e) => e.nextAttemptAt - now);
  return waiting.length ? Math.max(0, Math.min(...waiting)) : null;
}

/** An order the factory has not acknowledged yet (counted at logout, G6). */
export function isUnsent(entry: OutboxEntry): boolean {
  return entry.state !== "received";
}

export interface OutboxStore {
  all(): Promise<OutboxEntry[]>;
  put(entry: OutboxEntry): Promise<void>;
  remove(localId: string): Promise<void>;
}

export interface SyncDeps {
  store: OutboxStore;
  send: (entry: OutboxEntry) => Promise<SendResult>;
  now: () => number;
  random: () => number;
}

export class SyncEngine {
  private paused = false;
  private running: Promise<void> | null = null;

  constructor(private readonly deps: SyncDeps) {}

  get isPaused(): boolean {
    return this.paused;
  }

  /** After a sign-in: send again. */
  resume(): void {
    this.paused = false;
  }

  /** On app start: an order left "sending" by a closed tab goes back to "saved" (its key makes a resend safe). */
  async recover(): Promise<void> {
    for (const e of await this.deps.store.all()) {
      if (e.state === "sending") await this.deps.store.put({ ...e, state: "saved" });
    }
  }

  /** Send every due order once, one at a time. `force` ignores the backoff ("Send now"). */
  runOnce(force = false): Promise<void> {
    if (this.running) return this.running;
    this.running = this.run(force).finally(() => {
      this.running = null;
    });
    return this.running;
  }

  private async run(force: boolean): Promise<void> {
    if (this.paused) return;
    const now = this.deps.now();
    const all = await this.deps.store.all();
    const due = force
      ? all
          .filter((e) => e.state === "saved")
          .sort((a, b) => a.capturedAt.localeCompare(b.capturedAt))
      : dueEntries(all, now);
    for (const entry of due) {
      await this.deps.store.put({ ...entry, state: "sending" });
      let result: SendResult;
      try {
        result = await this.deps.send(entry);
      } catch {
        result = { kind: "network" };
      }
      const applied = applyResult(entry, result, this.deps.now(), this.deps.random());
      await this.deps.store.put(applied.entry);
      if (applied.pause) {
        this.paused = true;
        return;
      }
    }
  }
}

/** An in-memory store (tests, and a fallback when IndexedDB is unavailable). */
export class MemoryStore implements OutboxStore {
  readonly rows = new Map<string, OutboxEntry>();
  all(): Promise<OutboxEntry[]> {
    return Promise.resolve([...this.rows.values()]);
  }
  put(entry: OutboxEntry): Promise<void> {
    this.rows.set(entry.localId, entry);
    return Promise.resolve();
  }
  remove(localId: string): Promise<void> {
    this.rows.delete(localId);
    return Promise.resolve();
  }
}

/** A UUIDv7 (RFC 9562): 48-bit Unix ms timestamp, version 7, variant 10, random rest. */
export function uuidv7(now: number = Date.now(), bytes?: Uint8Array): string {
  const b = bytes ?? crypto.getRandomValues(new Uint8Array(16));
  let ts = BigInt(now);
  for (let i = 5; i >= 0; i--) {
    b[i] = Number(ts & 0xffn);
    ts >>= 8n;
  }
  b[6] = (b[6]! & 0x0f) | 0x70;
  b[8] = (b[8]! & 0x3f) | 0x80;
  const hex = [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
