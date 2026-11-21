import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useSession } from "../lib/sessionContext";
import { sendOrder } from "./api";
import { cacheGet, cachePut, dexieStore, wipeDevice } from "./db";
import { OutboxContext, type NewOrder, type OutboxState } from "./outboxContext";
import { isUnsent, msUntilNext, SyncEngine, uuidv7, type OutboxStore } from "./sync";
import type { OutboxEntry, SendResult } from "./types";

/**
 * Runs the outbox for a signed-in user who can take orders. Sync runs on app start, on the browser's `online`
 * event, and on a timer that follows the backoff (G5). The Background Sync API is not used.
 */
export function OutboxProvider({
  children,
  store = dexieStore,
  send = sendOrder,
  wipeStorage = wipeDevice,
}: {
  children: ReactNode;
  store?: OutboxStore;
  send?: (entry: OutboxEntry) => Promise<SendResult>;
  wipeStorage?: () => Promise<void>;
}) {
  const { me } = useSession();
  const canOrder = !!me?.permissions.includes("order.create");
  const [entries, setEntries] = useState<OutboxEntry[]>([]);
  const [ready, setReady] = useState(false);
  const [paused, setPaused] = useState(false);
  const [online, setOnline] = useState(() =>
    typeof navigator === "undefined" ? true : navigator.onLine,
  );
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(async () => {
    try {
      setEntries(await store.all());
    } catch {
      setEntries([]);
    }
  }, [store]);

  const watched = useMemo<OutboxStore>(
    () => ({
      all: () => store.all(),
      put: async (e) => {
        await store.put(e);
        await refresh();
      },
      remove: async (id) => {
        await store.remove(id);
        await refresh();
      },
    }),
    [store, refresh],
  );

  const engine = useMemo(
    () => new SyncEngine({ store: watched, send, now: () => Date.now(), random: Math.random }),
    [watched, send],
  );

  const schedule = useCallback(async () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    if (engine.isPaused) return;
    const wait = msUntilNext(await store.all(), Date.now());
    if (wait !== null) {
      timer.current = setTimeout(() => {
        void engine.runOnce().then(() => {
          setPaused(engine.isPaused);
          void schedule();
        });
      }, wait);
    }
  }, [engine, store]);

  const pump = useCallback(
    async (force = false) => {
      await engine.runOnce(force);
      setPaused(engine.isPaused);
      await schedule();
    },
    [engine, schedule],
  );

  // Start: a phone used by someone else is wiped first; then recover, send, and schedule.
  useEffect(() => {
    if (!me || !canOrder) {
      setReady(true);
      return;
    }
    let live = true;
    void (async () => {
      const owner = await cacheGet<string>("owner");
      if (owner && owner.value !== me.user.id) await wipeStorage();
      await cachePut("owner", me.user.id);
      engine.resume();
      await engine.recover();
      if (!live) return;
      await refresh();
      setReady(true);
      await pump();
    })();
    return () => {
      live = false;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [me, canOrder, engine, refresh, pump, wipeStorage]);

  useEffect(() => {
    const up = () => {
      setOnline(true);
      if (canOrder) void pump(true);
    };
    const down = () => setOnline(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    return () => {
      window.removeEventListener("online", up);
      window.removeEventListener("offline", down);
    };
  }, [canOrder, pump]);

  const save = useCallback(
    async (order: NewOrder) => {
      const now = Date.now();
      const entry: OutboxEntry = {
        ...order,
        localId: uuidv7(now),
        key: uuidv7(now),
        capturedAt: new Date(now).toISOString(),
        state: "saved",
        attempts: 0,
        nextAttemptAt: now,
      };
      await watched.put(entry);
      void pump();
      return entry.localId;
    },
    [watched, pump],
  );

  const discard = useCallback((localId: string) => watched.remove(localId), [watched]);
  const sendNow = useCallback(() => pump(true), [pump]);

  const wipe = useCallback(async () => {
    if (timer.current) clearTimeout(timer.current);
    await wipeStorage();
    setEntries([]);
  }, [wipeStorage]);

  const value = useMemo<OutboxState>(
    () => ({
      ready,
      entries,
      unsentCount: entries.filter(isUnsent).length,
      paused,
      online,
      save,
      discard,
      sendNow,
      wipe,
    }),
    [ready, entries, paused, online, save, discard, sendNow, wipe],
  );
  return <OutboxContext.Provider value={value}>{children}</OutboxContext.Provider>;
}
