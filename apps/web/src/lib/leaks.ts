import { plain } from "./plain";
import type { Explained } from "./explained";

/** GET /api/runs/{id}/costing (ADR-0014). Every number is an exact decimal string from the database. */
export interface Component {
  kind: string;
  label: string;
  item_code: string | null;
  value: string;
  direction: "UNFAVOURABLE" | "FAVOURABLE" | "NONE";
  note: string | null;
  explained: Explained;
}

export interface Costing {
  run_id: string;
  run_no: string;
  cost_status: string;
  run_date: string;
  lots: { pack_spec: string; lot_no: string | null; good_units: number; lot_value: string }[];
  cost: {
    materials: Explained;
    conversion: Explained;
    total: Explained;
    per_good_unit: Explained | null;
    lots: Explained[];
    written_off: string;
  };
  waterfall: {
    actual: Explained;
    standard: Explained;
    total: Explained;
    direction: string;
    components: Component[];
  } | null;
  waterfall_unavailable: string | null;
  sensitivity: Record<
    string,
    {
      posts: boolean;
      total: Explained;
      per_good_unit_display: string | null;
      unit: string;
      book_value_used_for: string[];
    }
  >;
  note: string;
}

/** Screen words for a code or label: "cooking_oil" -> "cooking oil", "MURUKKU-200G" -> "Murukku 200 g". */
export const words = (code: string | null) => plain(code);

/** Possibilities to verify, worded as checks, never as causes (MASTER_PACK MP07). */
export function checkFor(c: Component, runNo: string): string | null {
  if (c.value === "0.00" || c.kind === "ROUNDING") return null;
  const item = words(c.item_code);
  const favourable = c.direction === "FAVOURABLE";
  switch (c.kind) {
    case "YIELD":
      return `Check fill weights, breakage and the process log for batch ${runNo}: fewer good packets were made than the bulk allowed.`;
    case "USAGE":
      if (favourable)
        return `Confirm the count of ${item} for batch ${runNo}: less was used than the standard.`;
      if (c.note) return `Check sealing and handling of ${item} for batch ${runNo} (${c.note}).`;
      return `Check the issue slips and top-ups of ${item} for batch ${runNo}: more was used than the recipe needs.`;
    case "PRICE":
      return favourable
        ? `Confirm the purchase price of ${item}: it came in below the standard rate.`
        : `Check the purchase price of ${item} against the standard rate.`;
    case "CONVERSION":
      return `Check labour hours and gas readings for batch ${runNo} against the standard.`;
    default:
      return `Check ${c.label} for batch ${runNo}.`;
  }
}
