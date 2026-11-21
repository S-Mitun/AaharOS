import Dexie, { type Table } from "dexie";
import type { OutboxStore } from "./sync";
import type { OutboxEntry } from "./types";

/**
 * What the phone stores (G6, docs/security.md): the outbox, and a small cache of the assigned customers, the priced
 * catalog, the last order per customer and the salesman's own orders of the last 30 days. Logout deletes the whole
 * database. Nothing else (no tokens: they live in httpOnly cookies).
 */
export const DB_NAME = "aaharos-salesman";

interface CacheRow {
  key: string;
  value: unknown;
  savedAt: number;
}

class SalesDb extends Dexie {
  outbox!: Table<OutboxEntry, string>;
  cache!: Table<CacheRow, string>;

  constructor() {
    super(DB_NAME);
    this.version(1).stores({ outbox: "localId, state", cache: "key" });
  }
}

let db: SalesDb | null = null;

function open(): SalesDb {
  db ??= new SalesDb();
  return db;
}

export const dexieStore: OutboxStore = {
  all: () => open().outbox.toArray(),
  put: async (entry) => {
    await open().outbox.put(entry);
  },
  remove: async (localId) => {
    await open().outbox.delete(localId);
  },
};

export async function cachePut(key: string, value: unknown): Promise<void> {
  try {
    await open().cache.put({ key, value, savedAt: Date.now() });
  } catch {
    // a full or blocked IndexedDB only loses the offline copy; the screen still shows live data
  }
}

export async function cacheGet<T>(key: string): Promise<{ value: T; savedAt: number } | null> {
  try {
    const row = await open().cache.get(key);
    return row ? { value: row.value as T, savedAt: row.savedAt } : null;
  } catch {
    return null;
  }
}

/** Logout (G6): delete the whole database from this device. */
export async function wipeDevice(): Promise<void> {
  const current = db;
  db = null;
  current?.close();
  await Dexie.delete(DB_NAME);
}
