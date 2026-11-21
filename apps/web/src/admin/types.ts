import type { Explained } from "../lib/explained";

/** The admin's order inbox (MP09). Money and quantities are exact strings from the API. */

export interface InboxRow {
  id: string;
  order_no: string;
  order_date: string;
  received_at: string;
  status: string;
  customer_name: string | null;
  packets: string;
  value_ex_tax: string;
  short: boolean;
  stale: boolean;
  waiting: boolean;
}

export interface CardLine {
  line_no: number;
  item_id: string;
  item_code: string;
  item_name: string;
  requested: string;
  approved: string;
  backordered: string;
  open: string;
  price_captured: string;
  price_final: string | null;
  amend_reason: string | null;
  price_current: string | null;
  available: Explained;
  shortage: Explained;
  can_send_now: string;
  next_batch: { run_no: string; run_date: string; status: string; planned_packets: string } | null;
}

export interface OrderCard {
  id: string;
  order_no: string;
  order_date: string;
  status: string;
  captured_at: string | null;
  received_at: string;
  customer: { id: string; code: string; name: string; kind: string; state_code: string };
  salesman: { id: string; name: string | null } | null;
  price_list: { code: string; version: number } | null;
  stale: boolean;
  stale_detail: { in_force_price_list: { code: string; version: number } | null } | null;
  timeline: { from_status: string | null; to_status: string; at: string; reason: string | null }[];
  card_lines: CardLine[];
  shortage_total: string;
  credit: {
    limit: string | null;
    outstanding: Explained;
    exposure: Explained;
    over_limit: boolean;
  };
  stale_choice_needed: boolean;
  waiting: boolean;
  actions: string[];
  decision?: { status: string; summary: string };
}
