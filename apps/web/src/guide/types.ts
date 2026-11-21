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

/** Sidebar groups, in order (G9). */
export const GROUPS = [
  "Guide",
  "Salesman",
  "Admin",
  "Production",
  "Owner",
  "Auditor",
  "Judge",
] as const;
export type Group = (typeof GROUPS)[number];

export interface Screen {
  /** Full name, used by the tour ("Salesman app → New order"). */
  name: string;
  /** Short label for the sidebar. */
  label: string;
  /** Route inside this app. Unbuilt screens still have one: it opens the "Coming in MPxx" page. */
  route: string;
  /** Master prompt that builds it. */
  mp: string;
  built: boolean;
  group: Group;
  /** A plain glyph shown beside the label (decorative). */
  icon: string;
  /** What the screen does, in one line. */
  description: string;
  /** Permission a signed-in user needs to see it in the sidebar. None = everyone. The API still enforces it. */
  permission?: string;
  /** Not listed in the sidebar (reached from another screen). It still has a route. */
  hidden?: boolean;
}
