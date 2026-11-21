import { createContext, useContext } from "react";
import type { OutboxEntry, OutboxLine } from "./types";

export interface NewOrder {
  customerId: string;
  customerName: string;
  priceListId: string;
  priceListLabel: string;
  lines: OutboxLine[];
}

export interface OutboxState {
  /** False until the outbox has been read from the phone. */
  ready: boolean;
  entries: OutboxEntry[];
  /** Orders the factory has not acknowledged yet. */
  unsentCount: number;
  /** True after a 401: saved orders wait for a new sign-in. */
  paused: boolean;
  online: boolean;
  /** Save to the phone first (G5), then try to send. Returns the local id. */
  save: (order: NewOrder) => Promise<string>;
  discard: (localId: string) => Promise<void>;
  sendNow: () => Promise<void>;
  /** Logout (G6): delete everything this app stored on the device. */
  wipe: () => Promise<void>;
}

export const OutboxContext = createContext<OutboxState | null>(null);

export function useOutbox(): OutboxState {
  const s = useContext(OutboxContext);
  if (!s) throw new Error("useOutbox needs an OutboxProvider");
  return s;
}
