import type { Unit } from "./types";

/** NIT's "Results we will check" table (brief section 5), each row bound to oracle keys and scoreboard rows. */
export interface Check {
  label: string;
  keys: string[];
  unit?: Unit;
  assertions: number[];
  note?: string;
}

export const NIT_CHECKS: Check[] = [
  {
    label: "Flour closing balance",
    keys: ["nit_expected.flour_closing_kg"],
    unit: "kg",
    assertions: [1],
  },
  {
    label: "Oil closing balance",
    keys: ["nit_expected.oil_closing_L"],
    unit: "L",
    assertions: [2],
  },
  {
    label: "Pouches closing balance",
    keys: ["nit_expected.pouches_closing"],
    unit: "pieces",
    assertions: [3],
  },
  {
    label: "Finished goods after run",
    keys: ["nit_expected.fg_after_run_packets"],
    unit: "packets",
    assertions: [4],
  },
  {
    label: "Finished goods after Retailer A dispatch",
    keys: ["nit_expected.fg_after_dispatch_A_packets"],
    unit: "packets",
    assertions: [5],
  },
  {
    label: "Yield variance (flagged)",
    keys: ["nit_expected.yield_variance_percent"],
    unit: "±%",
    assertions: [6],
  },
  {
    label: "Oil variance (flagged)",
    keys: ["nit_expected.oil_variance_percent"],
    unit: "±%",
    assertions: [7],
  },
  {
    label: "Retailer A invoice: taxable / CGST / SGST / total",
    keys: [
      "nit_expected.invoice_A.taxable",
      "nit_expected.invoice_A.cgst",
      "nit_expected.invoice_A.sgst",
      "nit_expected.invoice_A.total",
    ],
    unit: "INR",
    assertions: [8, 9, 10, 11],
  },
  {
    label: "Retailer A outstanding",
    keys: ["nit_expected.outstanding_A"],
    unit: "INR",
    assertions: [12],
  },
  {
    label: "Distributor B shortage (flagged, not invoiced)",
    keys: ["nit_expected.distributor_B.shortage"],
    unit: "packets",
    assertions: [13],
  },
  {
    label: "Distributor B tax if invoiced",
    keys: ["nit_expected.distributor_B.tax_regime"],
    assertions: [14],
  },
  {
    label: "Cost per good packet",
    keys: ["aaharos_expected.run_cost.cost_per_good_packet"],
    unit: "INR/packet",
    assertions: [18],
    note: "Our figure: weighted-average cost, labour and gas assigned to the batch, divided by good packets.",
  },
];
