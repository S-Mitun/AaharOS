import type { OutboxState } from "./types";

export type Tone = "ok" | "todo" | "warn" | "bad" | "info";

/** G5 states and server statuses, as icon + word + colour. */
export const PHONE_STATUS: Record<OutboxState, [Tone, string]> = {
  saved: ["todo", "Saved on phone"],
  sending: ["info", "Sending"],
  received: ["ok", "Received by factory"],
  attention: ["bad", "Needs attention"],
};

export const SERVER_STATUS: Record<string, [Tone, string]> = {
  SUBMITTED: ["ok", "Received by factory"],
  APPROVED: ["ok", "Approved"],
  PART_APPROVED: ["warn", "Part approved"],
  REJECTED: ["bad", "Rejected"],
  INVOICED: ["ok", "Invoiced"],
  DISPATCHED: ["ok", "Dispatched"],
  CANCELLED: ["bad", "Cancelled"],
};

export function savedAtText(savedAt: number | null): string {
  if (!savedAt) return "";
  return new Date(savedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
