import { ApiError, apiGet } from "../lib/api";
import { cacheGet, cachePut } from "./db";
import type {
  Catalog,
  Customer,
  LastOrder,
  OutboxEntry,
  SendResult,
  ServerOrderRow,
} from "./types";

/** Send one outbox order. Never throws: every outcome is a SendResult the sync engine understands. */
export async function sendOrder(entry: OutboxEntry): Promise<SendResult> {
  const body = JSON.stringify({
    customer_id: entry.customerId,
    price_list_id: entry.priceListId,
    captured_at: entry.capturedAt,
    lines: entry.lines.map((l) => ({ item_id: l.itemId, qty: l.qty, price_ex_tax: l.price })),
  });
  const post = () =>
    fetch("/api/orders", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "Idempotency-Key": entry.key },
      body,
    });
  try {
    let res = await post();
    if (res.status === 401) {
      const refreshed = await fetch("/api/auth/refresh", {
        method: "POST",
        credentials: "same-origin",
      });
      if (refreshed.ok) res = await post();
    }
    const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    if (res.ok && typeof data.order_no === "string") {
      return {
        kind: "ok",
        status: res.status,
        order: {
          id: String(data.id),
          order_no: data.order_no,
          status: String(data.status),
          stale: data.stale === true,
        },
      };
    }
    const err = (data.error ?? {}) as { code?: string; message?: string };
    return {
      kind: "http",
      status: res.status,
      code: err.code ?? `http_${res.status}`,
      message: err.message ?? `The factory answered ${res.status}.`,
    };
  } catch {
    return { kind: "network" };
  }
}

/** Live data when online; the copy saved on this phone when not (G6). */
export interface Loaded<T> {
  data: T;
  offline: boolean;
  savedAt: number | null;
}

async function cached<T>(key: string, load: () => Promise<T>): Promise<Loaded<T>> {
  try {
    const data = await load();
    await cachePut(key, data);
    return { data, offline: false, savedAt: null };
  } catch (e) {
    // only "no connection" or a server failure falls back to the copy; a refusal (401/403/404) is shown as such
    const unreachable = !(e instanceof ApiError) || e.status >= 500;
    const copy = unreachable ? await cacheGet<T>(key) : null;
    if (copy) {
      return { data: copy.value, offline: true, savedAt: copy.savedAt };
    }
    throw e;
  }
}

export const loadCustomers = () =>
  cached(
    "customers",
    async () => (await apiGet<{ customers: Customer[] }>("/api/customers")).customers,
  );

export const loadCatalog = (customerId: string) =>
  cached(`catalog:${customerId}`, () =>
    apiGet<Catalog>(`/api/sales/catalog?customer_id=${encodeURIComponent(customerId)}`),
  );

export const loadLastOrder = (customerId: string) =>
  cached(`last:${customerId}`, async () => {
    const r = await apiGet<{ last_order: LastOrder | null }>(
      `/api/sales/customers/${encodeURIComponent(customerId)}/last-order`,
    );
    return r.last_order;
  });

export const loadMyOrders = () =>
  cached(
    "orders",
    async () => (await apiGet<{ orders: ServerOrderRow[] }>("/api/orders?days=30")).orders,
  );
