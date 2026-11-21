import { packetsTimesPrice, sumRupees } from "../lib/decimal";
import type { OutboxEntry } from "./types";

export function entryPackets(e: OutboxEntry): string {
  return String(e.lines.reduce((n, l) => n + Number(l.qty), 0));
}

/** The estimate shown before the factory confirms: Σ packets × list price, exactly. */
export function entryTotal(e: OutboxEntry): string {
  return sumRupees(e.lines.map((l) => packetsTimesPrice(l.qty, l.price)));
}
