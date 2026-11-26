import type { Explained } from "../lib/explained";

/** Shapes of /api/trace (MP13, ADR-0020). Every number is a string or an Explained value from the API. */
export type LotKind = "batch_lot" | "supplier_lot" | "opening_lot";

export interface LotRow {
  lot_id: string;
  lot_no: string;
  kind: LotKind;
  kind_label: string;
  item_id: string;
  item_code: string;
  item_name: string;
  mfg_date: string | null;
  best_before: string | null;
}

export interface SourceLabel {
  kind: "supplier_lot" | "no_lot" | "opening" | "other";
  label: string;
  date: string;
  lot_id?: string;
  lot_no?: string;
  supplier?: string;
  receipt_no?: string;
  source: { type: string; id: string };
}

export interface Moved {
  document: string;
  direction: "ISSUE" | "RETURN";
  posting_date: string;
  qty: Explained;
  source: { type: string; id: string };
}

export interface Material extends Moved {
  item_code: string;
  store: string;
  may_contain: SourceLabel[];
}

export interface Batch {
  run_id: string;
  run_no: string;
  status: string;
  run_date: string;
  completed_at: string | null;
  recipe: { code: string; version: number; version_id: string } | null;
  packs: { code: string; version: number; version_id: string }[];
  operator: string | null;
  lots: { lot_id: string; lot_no: string; pack_code: string | null; good_units: number | null }[];
  issues?: Moved[];
}

export interface DispatchRow {
  dispatch_id: string;
  dispatch_no: string;
  dispatch_date: string;
  invoice_id: string;
  invoice_no: string;
  customer_id: string;
  customer_code: string;
  customer_name: string;
  packets: string;
}

export interface ForwardLot extends LotRow {
  made: Explained | null;
  dispatched: Explained;
  on_hand: Explained;
  dispatches: DispatchRow[];
}

export interface SupplierBackward {
  store: string | null;
  receipts: {
    receipt_id: string;
    receipt_no: string;
    status: string;
    received_on: string;
    supplier: string;
    accepted: Explained;
  }[];
  never_accepted: boolean;
  may_still_be_in_store: boolean;
  batches: Batch[];
  note: string;
}

export interface BatchBackward {
  batch: Batch | null;
  materials: Material[];
  text?: string;
}

export interface Trace {
  lot: LotRow;
  note: string;
  backward: SupplierBackward | BatchBackward;
  forward: ForwardLot[];
}

export interface Recall {
  simulation: true;
  note: string;
  may_contain_note: string | null;
  subject: string;
  lot: LotRow;
  batches: Batch[];
  lots: ForwardLot[];
  customers: {
    customer_id: string;
    customer_code: string;
    customer_name: string;
    packets: Explained;
    invoice_nos: string[];
    lot_nos: string[];
    last_dispatch: string;
  }[];
  totals: { made: Explained; dispatched: Explained; on_hand: Explained; customers: string };
  notice: string;
}

export const isSupplier = (b: Trace["backward"]): b is SupplierBackward => "receipts" in b;

export interface OilLog {
  date_from: string;
  date_to: string;
  threshold_l_per_day: string;
  tpc_limit_pct: string;
  records_required: boolean;
  days: {
    date: string;
    litres: Explained;
    above_threshold: boolean;
    sessions: {
      run_id: string;
      run_no: string;
      fresh_l: string;
      topup_l: string;
      discard_l: string;
      tpc_pct: string | null;
      discard_oil: boolean;
    }[];
  }[];
  note: string;
}

export interface FillWeights {
  date_from: string;
  date_to: string;
  tolerances: { declared_g: string; tolerance_g: string }[];
  runs: {
    run_id: string;
    run_no: string;
    run_date: string;
    pack_code: string;
    declared_g: string;
    good_units: string;
    samples: string[];
    mean_net: Explained;
    over_per_packet: Explained;
    cost_per_kg: Explained;
    giveaway: Explained;
    tolerance_g: string | null;
    short_limit_g: string | null;
    short_samples: string[];
    short_fill_alert: boolean;
  }[];
  note: string;
}

export interface PassportLabelData {
  token: string;
  path: string;
  url: string;
  qr_svg: string;
}
