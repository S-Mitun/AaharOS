import { describe, expect, it } from "vitest";
import {
  applyResult,
  backoffMs,
  dueEntries,
  MAX_DELAY_MS,
  MemoryStore,
  msUntilNext,
  SyncEngine,
  uuidv7,
} from "./sync";
import type { OutboxEntry, SendResult } from "./types";

const T0 = 1_795_000_000_000;

function entry(over: Partial<OutboxEntry> = {}): OutboxEntry {
  return {
    localId: "local-1",
    key: "0190e0b0-0000-7000-8000-000000000001",
    customerId: "c1",
    customerName: "DEMO Retailer A",
    priceListId: "pl1",
    priceListLabel: "GENERAL v1",
    lines: [{ itemId: "i1", name: "DEMO murukku 200g", qty: "150", price: "50.00" }],
    capturedAt: new Date(T0).toISOString(),
    state: "saved",
    attempts: 0,
    nextAttemptAt: T0,
    ...over,
  };
}

const OK: SendResult = {
  kind: "ok",
  status: 201,
  order: { id: "o1", order_no: "SO/26-27/000001", status: "SUBMITTED", stale: false },
};
const http = (status: number, code = `http_${status}`): SendResult => ({
  kind: "http",
  status,
  code,
  message: `refused ${status}`,
});

describe("backoff (G5)", () => {
  it("starts at 2 s, doubles, and stops at 5 minutes, with jitter of ±20%", () => {
    expect(backoffMs(1, 0.5)).toBe(2_000);
    expect(backoffMs(2, 0.5)).toBe(4_000);
    expect(backoffMs(3, 0.5)).toBe(8_000);
    expect(backoffMs(20, 0.5)).toBe(MAX_DELAY_MS);
    expect(backoffMs(3, 0)).toBe(6_400);
    expect(backoffMs(3, 1)).toBe(9_600);
    expect(backoffMs(30, 1)).toBe(MAX_DELAY_MS);
  });
});

describe("one send attempt", () => {
  it("is Received only with the server's acknowledgement and order number", () => {
    const { entry: e, pause } = applyResult(entry(), OK, T0, 0.5);
    expect(e.state).toBe("received");
    expect(e.serverOrder?.orderNo).toBe("SO/26-27/000001");
    expect(pause).toBe(false);
  });

  it.each([{ kind: "network" } as SendResult, http(500), http(503), http(408), http(429)])(
    "keeps the order Saved on phone and backs off: %o",
    (result) => {
      const { entry: e } = applyResult(entry({ attempts: 1 }), result, T0, 0.5);
      expect(e.state).toBe("saved");
      expect(e.attempts).toBe(2);
      expect(e.nextAttemptAt).toBe(T0 + 4_000);
      expect(e.serverOrder).toBeUndefined();
    },
  );

  it.each([
    http(422, "price_mismatch"),
    http(409, "idempotency_key_reused"),
    http(403, "customer_not_assigned"),
    http(404),
  ])("moves a refusal to Needs attention with the reason: %o", (result) => {
    const { entry: e } = applyResult(entry(), result, T0, 0.5);
    expect(e.state).toBe("attention");
    expect(e.lastError?.code).toBe((result as { code: string }).code);
  });

  it("pauses on 401 and keeps the order", () => {
    const { entry: e, pause } = applyResult(entry(), http(401, "unauthenticated"), T0, 0.5);
    expect(pause).toBe(true);
    expect(e.state).toBe("saved");
  });
});

describe("the engine", () => {
  function setup(results: SendResult[]) {
    const store = new MemoryStore();
    let now = T0;
    const sent: string[] = [];
    const engine = new SyncEngine({
      store,
      now: () => now,
      random: () => 0.5,
      send: (e) => {
        sent.push(e.key);
        return Promise.resolve(results.shift() ?? OK);
      },
    });
    return { store, engine, sent, tick: (ms: number) => (now += ms) };
  }

  it("offline, then back online: the order reaches the server exactly once", async () => {
    const { store, engine, sent, tick } = setup([{ kind: "network" }, { kind: "network" }, OK]);
    await store.put(entry());
    await engine.runOnce();
    expect((await store.all())[0]?.state).toBe("saved");
    await engine.runOnce(); // not due yet: backoff holds it
    expect(sent).toHaveLength(1);
    tick(2_000);
    await engine.runOnce();
    tick(4_000);
    await engine.runOnce();
    const [done] = await store.all();
    expect(done?.state).toBe("received");
    expect(sent).toEqual([done?.key, done?.key, done?.key]); // the same Idempotency-Key every time
    tick(600_000);
    await engine.runOnce();
    expect(sent).toHaveLength(3); // a received order is never sent again
  });

  it("Send now ignores the backoff", async () => {
    const { store, engine, sent } = setup([{ kind: "network" }, OK]);
    await store.put(entry());
    await engine.runOnce();
    await engine.runOnce(true);
    expect(sent).toHaveLength(2);
    expect((await store.all())[0]?.state).toBe("received");
  });

  it("stops at a 401 until resumed, then sends", async () => {
    const { store, engine, sent } = setup([http(401, "unauthenticated"), OK]);
    await store.put(entry({ localId: "a", capturedAt: "2026-11-21T09:00:00Z" }));
    await store.put(entry({ localId: "b", key: "k-b", capturedAt: "2026-11-21T09:05:00Z" }));
    await engine.runOnce();
    expect(engine.isPaused).toBe(true);
    expect(sent).toHaveLength(1);
    await engine.runOnce();
    expect(sent).toHaveLength(1);
    engine.resume();
    await engine.runOnce(true);
    expect((await store.all()).map((e) => e.state)).toEqual(["received", "received"]);
  });

  it("recovers an order left Sending by a closed tab", async () => {
    const { store, engine } = setup([]);
    await store.put(entry({ state: "sending" }));
    await engine.recover();
    expect((await store.all())[0]?.state).toBe("saved");
  });

  it("orders due entries oldest first and knows when the next is due", () => {
    const a = entry({ localId: "a", capturedAt: "2026-11-21T10:00:00Z" });
    const b = entry({ localId: "b", capturedAt: "2026-11-21T09:00:00Z" });
    const later = entry({ localId: "c", nextAttemptAt: T0 + 5_000 });
    expect(dueEntries([a, b, later], T0).map((e) => e.localId)).toEqual(["b", "a"]);
    expect(msUntilNext([later], T0)).toBe(5_000);
    expect(msUntilNext([entry({ state: "received" })], T0)).toBeNull();
  });
});

describe("UUIDv7 keys (G4)", () => {
  it("carries the time, version 7 and the RFC variant", () => {
    const id = uuidv7(T0, new Uint8Array(16));
    expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    expect(parseInt(id.replace(/-/g, "").slice(0, 12), 16)).toBe(T0);
    expect(uuidv7()).not.toBe(uuidv7());
  });
});
