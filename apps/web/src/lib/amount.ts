import { roundDecimal } from "./decimal";
import { displayPlaces } from "./explained";
import { formatValue } from "./format";

/** "5855.00" INR -> "₹5,855.00"; "31.143617" INR/packet -> "₹31.14 / packet"; "10.5" L -> "10.5 L". */
export function formatAmount(value: string, unit: string): string {
  const places = displayPlaces(unit);
  const shown = places === null ? value : roundDecimal(value, places);
  if (unit === "INR") return formatValue(shown, "INR");
  if (unit.startsWith("INR/")) return `${formatValue(shown, "INR")} / ${unit.slice(4)}`;
  if (unit === "%") return formatValue(shown, "%");
  if (!unit) return formatValue(shown);
  const one = SINGULAR[unit];
  return `${formatValue(shown)} ${one && /^1(\.0*)?$/.test(shown) ? one : unit}`;
}

/** Count units that read in the singular for exactly one ("1 batch", not "1 batches"). */
const SINGULAR: Record<string, string> = {
  batches: "batch",
  packets: "packet",
  orders: "order",
  pieces: "piece",
};
