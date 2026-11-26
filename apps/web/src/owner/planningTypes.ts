import type { Explained } from "../lib/explained";

/** GET /api/planning/* (MP12, ADR-0019). Every number is an exact decimal string from the server. */
export interface DemandRow {
  item_code: string;
  open_packets: string;
  available: string;
  shortfall: string;
  value_per_packet: string;
  met_today: string;
}

export interface QtyRow {
  item_code: string;
  qty: string;
  unit: string;
  qty_base: string;
}

export interface Purchase extends QtyRow {
  item_id: string;
  needed_by: string;
  lead_time_days: number;
  explained: Explained;
}

export interface BatchPlan {
  date: string;
  capacity: string;
  status: string;
  demand: DemandRow[];
  batches: {
    pack_code: string;
    pack_version_id: string;
    recipe_version_id: string;
    batches: Explained | null;
    good_packets_per_batch: string;
  }[];
  value_met: string;
  materials_used: QtyRow[];
  materials_short: QtyRow[];
  purchases: Purchase[];
  note: string;
}

export interface RunwayPack {
  pack_code: string;
  pack_name: string;
  recipe: string;
  expected_good_per_batch: string;
  materials: {
    item_code: string;
    unit: string;
    available: string;
    per_batch: string;
    batches: Explained;
    binding: boolean;
  }[];
  binding: string[];
  full_batches: Explained;
}

export interface DraftPo {
  id: string;
  draft_no: string;
  status: string;
  created_at: string;
  note: string | null;
  lines: {
    item_code: string;
    qty: string;
    unit: string;
    needed_by: string;
    reason: string | null;
  }[];
}

export interface Action {
  kind: string;
  title: string;
  impact: Explained;
  link: string;
}

export interface Brief {
  date: string;
  cards: {
    orders: {
      today: { count: number; value: string };
      to_decide: { count: number; value: string };
      link: string;
    };
    available_vs_pending: { items: DemandRow[]; note: string | null; link: string };
    leaks: {
      top: { run_id: string; run_no: string; label: string; value: Explained; link: string }[];
      link: string;
    };
    runway: {
      packs: { pack_code: string; binding: string[]; full_batches: Explained }[];
      link: string;
    };
    money: {
      outstanding: string;
      overdue: Explained;
      past_msme_45_days: string;
      top_overdue: { customer_id: string; customer_name: string; overdue: string }[];
      link: string;
    };
  };
  actions: Action[];
}

export interface Attribution {
  order_id: string;
  order_no: string;
  lines: {
    item_id: string;
    item_name: string;
    shortage: number;
    attributed_to_yield_loss: Explained;
    would_have_been: number;
  }[];
}

/** "murukku_200g" → "murukku 200g": item codes read as words on screen. */
export const words = (code: string) => code.replace(/_/g, " ");
