import type { Explained } from "../lib/explained";

/** Invoices, dispatch and collections (MP10). Money and quantities are exact strings from the API. */

export interface ReadyOrder {
  order_id: string;
  order_no: string;
  status: string;
  customer_name: string;
  packets_to_invoice: string;
  value_ex_tax: string;
}

export interface InvoiceRow {
  id: string;
  invoice_no: string;
  invoice_date: string;
  customer_name: string;
  status: string;
  total: string;
  packets: string;
  dispatched: string;
  due_date: string;
}

export interface InvoiceView {
  id: string;
  invoice_no: string;
  invoice_date: string;
  due_date: string;
  status: string;
  cancel_reason: string | null;
  order_id: string | null;
  order_no: string | null;
  regime: string;
  place_of_supply: string;
  supplier: { name: string; state_label: string };
  customer: { id: string; name: string; gstin: string | null; state_label: string };
  lines: {
    line_no: number;
    item_id: string;
    item_name: string;
    hsn: string;
    qty: string;
    unit: string;
    rate: string;
    taxable: string;
    dispatched: string;
    taxes: { tax: string; rate_pct: string; amount: string }[];
  }[];
  taxable: string;
  by_tax: Record<string, string>;
  round_off: string;
  total: string;
  amount_in_words: string;
  lots: { lot_no: string; qty: string }[];
  paid: string;
  credited: string;
  outstanding: string;
  credit_notes: {
    id: string;
    credit_note_no: string;
    note_date: string;
    total: string;
    reason: string;
  }[];
  credit_note_no?: string;
}

export interface DispatchPreview {
  invoice_no: string;
  dispatch_date: string;
  lines: {
    item_id: string;
    item_name: string;
    invoiced: string;
    already_dispatched: string;
    now: string;
    fefo: boolean;
    picks: { lot_no: string; qty: string; value: string }[];
    stock_movement: string[];
  }[];
  cost_of_goods: string;
  consignment_value: string;
  eway: { required: boolean; reason: string; threshold: string; mock: boolean };
}

export interface DispatchView {
  id: string;
  dispatch_no: string;
  dispatch_date: string;
  eway: { required: boolean; reason: string | null; mock: boolean };
  lines: { item_name: string; lot_no: string; qty: string; override_reason: string | null }[];
}

export interface CollectionRow {
  customer_id: string;
  customer_name: string;
  outstanding: string;
  overdue: string;
  advance: string;
  open_invoices: number;
}

export interface Statement {
  customer: { id: string; name: string; payment_terms_days: number; msme_terms: boolean };
  as_of: string;
  outstanding: Explained;
  advance: string;
  invoices: {
    invoice_id: string;
    invoice_no: string;
    invoice_date: string;
    due_date: string;
    total: string;
    paid: string;
    credited: string;
    outstanding: string;
    overdue: boolean;
    days_overdue: number;
  }[];
  payments: {
    id: string;
    payment_no: string;
    received_on: string;
    amount: string;
    mode: string;
    reference: string | null;
  }[];
  payment_no?: string;
}
