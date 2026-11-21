/** Shapes the salesman app stores and the API returns (MP08). Money and quantities are exact strings. */

export interface Customer {
  id: string;
  code: string;
  name: string;
  kind: string;
  state_code: string;
  route_order: number | null;
}

export interface Product {
  item_id: string;
  code: string;
  name: string;
  price_ex_tax: string;
  units_per_carton: number | null;
  /** Whole packets available today, or null when the caller cannot read stock. A hint, never a promise. */
  available_today: string | null;
}

export interface Catalog {
  customer_id: string;
  price_list: { id: string; code: string; version: number; effective_from: string } | null;
  products: Product[];
  note: string;
}

export interface LastOrder {
  id: string;
  order_no: string;
  order_date: string;
  lines: { item_id: string; qty: string }[];
}

export interface ServerOrderRow {
  id: string;
  order_no: string;
  order_date: string;
  customer_id: string;
  customer_name: string | null;
  status: string;
  captured_at: string | null;
  received_at: string;
  packets: string;
  value_ex_tax: string;
  stale: boolean;
}

/** G5: where an order is. "received" only after the server's 201/200 with an order number. */
export type OutboxState = "saved" | "sending" | "received" | "attention";

export interface OutboxLine {
  itemId: string;
  name: string;
  qty: string; // whole packets
  price: string; // ex tax, as shown from the price list
}

export interface OutboxEntry {
  localId: string;
  /** The Idempotency-Key (UUIDv7), made when the order was saved on the phone. */
  key: string;
  customerId: string;
  customerName: string;
  priceListId: string;
  priceListLabel: string;
  lines: OutboxLine[];
  capturedAt: string; // ISO with offset
  state: OutboxState;
  attempts: number;
  nextAttemptAt: number; // epoch ms
  lastError?: { status: number; code: string; message: string };
  serverOrder?: { id: string; orderNo: string; status: string; stale: boolean };
}

export type SendResult =
  | {
      kind: "ok";
      status: number;
      order: { id: string; order_no: string; status: string; stale: boolean };
    }
  | { kind: "network" }
  | { kind: "http"; status: number; code: string; message: string };
