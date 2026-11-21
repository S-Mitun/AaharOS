/**
 * Exact decimal helpers for display. Values arrive from the API as strings ("31.143617") and are never turned into
 * JavaScript numbers: rounding and bar widths use BigInt on the digits.
 */

const DECIMAL = /^(-?)(\d+)(?:\.(\d+))?$/;

/** Round half up (away from zero) to `places` decimals: "31.143617" -> "31.14", "-4.255" -> "-4.26". */
export function roundDecimal(text: string, places: number): string {
  const m = DECIMAL.exec(text);
  if (!m) return text;
  const [, sign = "", int = "0", frac = ""] = m;
  if (frac.length <= places) {
    return `${sign}${int}${places ? `.${frac.padEnd(places, "0")}` : ""}`;
  }
  let kept = BigInt(int + frac.slice(0, places));
  if (frac.charCodeAt(places) - 48 >= 5) kept += 1n;
  const digits = kept.toString().padStart(places + 1, "0");
  const whole = digits.slice(0, digits.length - places);
  const out = places ? `${whole}.${digits.slice(digits.length - places)}` : whole;
  return sign && /[1-9]/.test(out) ? `-${out}` : out;
}

/** The value in hundredths as a BigInt ("307.2" -> 30720n): for proportions only, never displayed. */
export function toHundredths(text: string): bigint {
  const rounded = roundDecimal(text, 2);
  const m = DECIMAL.exec(rounded);
  if (!m) return 0n;
  const [, sign = "", int = "0", frac = "00"] = m;
  const v = BigInt(int + frac);
  return sign ? -v : v;
}

/** |value| / |max| as a whole percentage 0-100 (for a bar's width). */
export function sharePercent(value: string, max: string): number {
  const v = toHundredths(value);
  const m = toHundredths(max);
  const a = v < 0n ? -v : v;
  const b = m < 0n ? -m : m;
  if (b === 0n) return 0;
  return Number((a * 100n) / b);
}

function fromHundredths(v: bigint): string {
  const neg = v < 0n;
  const digits = (neg ? -v : v).toString().padStart(3, "0");
  return `${neg ? "-" : ""}${digits.slice(0, -2)}.${digits.slice(-2)}`;
}

/** Whole packets × a rupee price, exactly: ("150", "50.00") -> "7500.00". */
export function packetsTimesPrice(qty: string, price: string): string {
  return fromHundredths(BigInt(qty) * toHundredths(price));
}

/** Sum of rupee amounts, exactly, to paise. */
export function sumRupees(values: string[]): string {
  return fromHundredths(values.reduce((acc, v) => acc + toHundredths(v), 0n));
}

export function isNegative(text: string): boolean {
  return /^-/.test(text) && /[1-9]/.test(text);
}
