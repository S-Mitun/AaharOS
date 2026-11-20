import type { Unit } from "../guide/types";

/** Follow a dotted path ("nit_expected.invoice_A.total") into the oracle payload. */
export function lookup(payload: unknown, dotted: string): unknown {
  let node: unknown = payload;
  for (const part of dotted.split(".")) {
    if (node === null || typeof node !== "object" || !(part in node)) return undefined;
    node = (node as Record<string, unknown>)[part];
  }
  return node;
}

/** Group digits Indian-style (1,23,456) without converting to a float. */
function groupIndian(digits: string): string {
  if (digits.length <= 3) return digits;
  const last3 = digits.slice(-3);
  const rest = digits.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",");
  return `${rest},${last3}`;
}

/** Format an exact decimal string for display. Never parses to a JS number. */
export function formatValue(raw: unknown, unit?: Unit): string {
  if (raw === undefined || raw === null) return "—";
  if (typeof raw === "boolean") return unit === "yesno" ? (raw ? "Yes" : "No") : String(raw);
  const text = String(raw);
  const m = /^(-?)(\d+)(\.\d+)?$/.exec(text);
  if (!m) return text;
  const [, sign = "", int = "", frac = ""] = m;
  const signText = sign ? "−" : unit === "±%" ? "+" : "";
  const num = `${groupIndian(int)}${frac}`;
  switch (unit) {
    case "INR":
      return `${signText}₹${num}`;
    case "INR/kg":
      return `${signText}₹${num} / kg`;
    case "INR/packet":
      return `${signText}₹${num} / packet`;
    case "%":
    case "±%":
      return `${signText}${num}%`;
    case undefined:
    case "yesno":
      return `${signText}${num}`;
    default:
      return `${signText}${num} ${unit}`;
  }
}

/** Replace {dotted.key} placeholders in guide copy with oracle values. */
export function fillTemplate(text: string, payload: unknown): string {
  return text.replace(/\{([A-Za-z0-9_.]+)\}/g, (_, key: string) => {
    const v = lookup(payload, key);
    return v === undefined ? "…" : formatValue(v);
  });
}

/** All {placeholders} used in a piece of copy. */
export function placeholders(text: string): string[] {
  return [...text.matchAll(/\{([A-Za-z0-9_.]+)\}/g)].map((m) => m[1] ?? "");
}
