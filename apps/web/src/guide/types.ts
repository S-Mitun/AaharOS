export type Role = "Visitor" | "Salesman" | "Admin" | "Production" | "Owner" | "Auditor";

/** A value the visitor should see. `key` is a dotted path into the oracle payload from /api/guide/expected. */
export type Expectation =
  | { label: string; key: string; unit?: Unit; flagged?: boolean }
  | { label: string; text: string };

export type Unit =
  | "±%"
  | "INR"
  | "INR/kg"
  | "INR/packet"
  | "kg"
  | "L"
  | "%"
  | "packets"
  | "pieces"
  | "yesno";

export interface GuideStep {
  /** URL slug: /guide/<id> */
  id: string;
  /** NIT section 5 step number, when this card is one of the 9 steps. */
  nitStep?: number;
  title: string;
  who: { role: Role; login: string };
  /** Screen id from screens.ts. */
  screen: string;
  /** Plain-language actions. `{dotted.key}` placeholders are filled from the oracle. */
  actions: string[];
  expect: Expectation[];
  why: string;
  /** Benchmark scoreboard rows (MASTER_PACK Part C) that prove this step. */
  assertions: number[];
}

export interface Screen {
  name: string;
  /** Route inside this app once built. */
  route: string;
  /** Master prompt that builds it. */
  mp: string;
  built: boolean;
}
