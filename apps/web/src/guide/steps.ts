import type { GuideStep } from "./types";

/**
 * The guided tour: an intro, NIT's nine benchmark steps in order, and a finish card.
 * All numbers come from the oracle (benchmark/expected_results.yaml) through /api/guide/expected:
 * write them as {dotted.key} in text or as an Expectation `key`, never as literals.
 * Copy lives here (not in components) so it can be edited and translated (MP15) in one place.
 */
export const STEPS: GuideStep[] = [
  {
    id: "start",
    title: "Before you start",
    who: { role: "Visitor", login: "No login needed" },
    screen: "home",
    actions: [
      "Open the running app: the hosted demo link, or run `make up` and open http://localhost:5180.",
      "Keep this tour open. The Guide button (bottom right) brings you back to the right step from any screen.",
      "Every step tells you who does it, where to go, what to type, and the number you should see.",
      "Tap the ⓘ next to any figure in the app to see its formula and the record it came from.",
    ],
    expect: [
      { label: "Opening flour", key: "inputs.opening_stock.flour.qty", unit: "kg" },
      { label: "Opening cooking oil", key: "inputs.opening_stock.cooking_oil.qty", unit: "L" },
      {
        label: "Opening finished packets",
        key: "inputs.opening_stock.murukku_200g.qty",
        unit: "packets",
      },
      { label: "Variance tolerance", key: "config.variance_tolerance_percent", unit: "%" },
      { label: "GST rate (exercise)", key: "config.gst_rate_percent", unit: "%" },
    ],
    why: "The factory starts from NIT's opening stock. Everything after this is entered once, at its source.",
    assertions: [],
  },
  {
    id: "purchase",
    nitStep: 1,
    title: "Buy flour",
    who: { role: "Production", login: "Production supervisor" },
    screen: "purchases",
    actions: [
      "Open Purchases → New receipt.",
      "Supplier: DEMO Flour Mills. Item: Flour. Quantity {inputs.steps.1_purchase.qty} kg at ₹{inputs.steps.1_purchase.rate}/kg.",
      "Press Post receipt.",
      "Tap ⓘ next to the flour cost to see how the average was calculated.",
    ],
    expect: [
      {
        label: "Flour average cost (weighted average)",
        key: "aaharos_expected.flour_wac_after_purchase",
        unit: "INR/kg",
      },
    ],
    why: "A purchase is a stock movement with a source document. The average cost updates by itself.",
    assertions: [16],
  },
  {
    id: "issue",
    nitStep: 2,
    title: "Start a production batch",
    who: { role: "Production", login: "Production supervisor" },
    screen: "batch",
    actions: [
      "Open Production → New batch → Murukku 200 g, 1 batch. The Planned column fills from the recipe.",
      "In the Actual column enter flour {inputs.steps.2_issue.flour} kg, oil {inputs.steps.2_issue.cooking_oil} L, spice mix {inputs.steps.2_issue.spice_mix} kg.",
      "Look at the stock-impact preview: it shows every stock change before you post.",
    ],
    expect: [
      { label: "Flour left", key: "nit_expected.flour_closing_kg", unit: "kg" },
      { label: "Oil left", key: "nit_expected.oil_closing_L", unit: "L" },
      { label: "Spice mix left", key: "aaharos_expected.spice_closing_kg", unit: "kg" },
    ],
    why: "Raw stock goes down automatically. The oil entered is above the recipe, and the next step flags it.",
    assertions: [1, 2, 15],
  },
  {
    id: "output",
    nitStep: 3,
    title: "Record what the batch made",
    who: { role: "Production", login: "Production supervisor" },
    screen: "batch",
    actions: [
      "On the same batch card enter Good packets {inputs.steps.3_output.good_packets}, Damaged pouches {inputs.steps.3_output.damaged_pouches}, Cartons used {inputs.steps.3_output.cartons_used}.",
      "Pick a reason chip for the damaged pouches (for example Seal failure).",
      "Press Post batch once. A mistake is fixed with a reversal, never by deleting.",
    ],
    expect: [
      {
        label: "Finished packets in stock",
        key: "nit_expected.fg_after_run_packets",
        unit: "packets",
      },
      { label: "Pouches left", key: "nit_expected.pouches_closing", unit: "pieces" },
      { label: "Cartons left", key: "aaharos_expected.cartons_closing", unit: "pieces" },
      {
        label: "Yield variance",
        key: "nit_expected.yield_variance_percent",
        unit: "±%",
        flagged: true,
      },
      {
        label: "Oil variance",
        key: "nit_expected.oil_variance_percent",
        unit: "±%",
        flagged: true,
      },
      {
        label: "Pouches vs good packets",
        key: "aaharos_expected.flexible_standard_variances.pouch_vs_good_output_percent",
        unit: "±%",
        flagged: true,
      },
    ],
    why: "Packaging is measured against the good packets actually made, so damaged pouches show up instead of hiding inside the recipe total.",
    assertions: [3, 4, 6, 7, 15, 20],
  },
  {
    id: "order-a",
    nitStep: 4,
    title: "Salesman A takes an order on the phone",
    who: { role: "Salesman", login: "Salesman A" },
    screen: "salesOrder",
    actions: [
      "Sign in → tap “Salesman A” → type the DEMO password. You land on Today. (On a laptop, make the window narrow to see the phone layout.)",
      "Today → DEMO Retailer A → New order.",
      "Type {inputs.steps.4_order_A.qty} in the packets box (or tap “+1 carton” to add 20 at a time) → Save order.",
      "The order opens with its number and “Received by factory”. No network? It says “Saved on phone” and sends itself when the network is back: it never says “Received” before the factory confirms.",
    ],
    expect: [
      { label: "Packets ordered", key: "inputs.steps.4_order_A.qty", unit: "packets" },
      { label: "Order value ex-tax", key: "nit_expected.invoice_A.taxable", unit: "INR" },
      { label: "Status after Save", text: "Received by factory" },
    ],
    why: "No phone call, no WhatsApp, no re-typing: the order reaches the factory directly.",
    assertions: [],
  },
  {
    id: "invoice-a",
    nitStep: 5,
    title: "Admin approves, invoices and dispatches",
    who: { role: "Admin", login: "Factory admin" },
    screen: "orderInbox",
    actions: [
      "Order Inbox → Retailer A. “Available to promise” covers the order → Approve.",
      "Create invoice. Tamil Nadu to Tamil Nadu, so the tax splits into CGST + SGST.",
      "Download the invoice PDF, then Record dispatch. The oldest lot leaves first (FEFO).",
    ],
    expect: [
      { label: "Taxable value", key: "nit_expected.invoice_A.taxable", unit: "INR" },
      { label: "CGST", key: "nit_expected.invoice_A.cgst", unit: "INR" },
      { label: "SGST", key: "nit_expected.invoice_A.sgst", unit: "INR" },
      { label: "Invoice total", key: "nit_expected.invoice_A.total", unit: "INR" },
      {
        label: "Finished packets left",
        key: "nit_expected.fg_after_dispatch_A_packets",
        unit: "packets",
      },
      {
        label: "Sent from the opening lot",
        key: "aaharos_expected.fefo_dispatch_A.from_opening_lot",
        unit: "packets",
      },
      {
        label: "Sent from batch B-001",
        key: "aaharos_expected.fefo_dispatch_A.from_batch_B001",
        unit: "packets",
      },
    ],
    why: "One approval flows into the invoice, the stock and the customer's balance. Nothing is typed twice.",
    assertions: [5, 8, 9, 10, 11, 21, 22],
  },
  {
    id: "order-b",
    nitStep: 6,
    title: "Salesman B's order runs short",
    who: { role: "Salesman", login: "Salesman B, then Factory admin" },
    screen: "orderInbox",
    actions: [
      "Sign in as Salesman B: Today → DEMO Distributor B (Karnataka) → New order → {inputs.steps.6_order_B.qty} packets → Save order. The stock hint already warns it is short.",
      "As Admin, open the order. The card shows the shortage and three options: send what is available and backorder the rest, wait for the next batch, or reject.",
      "Do not invoice it: stock can never go below zero.",
    ],
    expect: [
      { label: "Requested", key: "nit_expected.distributor_B.requested", unit: "packets" },
      { label: "Available", key: "nit_expected.distributor_B.available", unit: "packets" },
      {
        label: "Shortage",
        key: "nit_expected.distributor_B.shortage",
        unit: "packets",
        flagged: true,
      },
      { label: "Tax if invoiced (other state)", key: "nit_expected.distributor_B.tax_regime" },
      {
        label: "IGST if sent in full",
        key: "aaharos_expected.distributor_B_options.full_120.igst",
        unit: "INR",
      },
      {
        label: "e-Way Bill required?",
        key: "aaharos_expected.distributor_B_options.full_120.eway_bill_required",
        unit: "yesno",
      },
      {
        label: "Shortage caused by this batch's lost packets",
        key: "aaharos_expected.shortage_attribution_B.caused_by_this_runs_yield_loss",
        unit: "packets",
      },
    ],
    why: "The two loops meet here: the packets lost in production are part of why this customer is short.",
    assertions: [13, 14, 23, 25],
  },
  {
    id: "payment",
    nitStep: 7,
    title: "Record Retailer A's payment",
    who: { role: "Admin", login: "Factory admin" },
    screen: "collections",
    actions: [
      "Collections → Record payment → Retailer A → ₹{inputs.steps.7_payment_A.amount}.",
      "Allocate it to the invoice from step 5.",
    ],
    expect: [{ label: "Retailer A still owes", key: "nit_expected.outstanding_A", unit: "INR" }],
    why: "Each customer's balance comes from invoices minus allocated payments, never from a typed number.",
    assertions: [12],
  },
  {
    id: "run-costs",
    nitStep: 8,
    title: "Add labour and gas, see cost per packet",
    who: { role: "Production", login: "Production supervisor" },
    screen: "batchCosts",
    actions: [
      "Open batch B-001 → Run costs → labour ₹{inputs.steps.8_run_costs.labour}, gas/power ₹{inputs.steps.8_run_costs.gas_power}.",
      "Open Where profit leaks to see where the money went, step by step from standard cost to actual.",
    ],
    expect: [
      { label: "Total batch cost", key: "aaharos_expected.run_cost.total", unit: "INR" },
      {
        label: "Cost per good packet",
        key: "aaharos_expected.run_cost.cost_per_good_packet",
        unit: "INR/packet",
      },
      {
        label: "Same batch with FIFO",
        key: "aaharos_expected.valuation_sensitivity.FIFO.per_packet",
        unit: "INR/packet",
      },
      {
        label: "Same batch with last price",
        key: "aaharos_expected.valuation_sensitivity.LAST.per_packet",
        unit: "INR/packet",
      },
      {
        label: "Cost above standard",
        key: "aaharos_expected.variance_waterfall.total_unfavourable",
        unit: "INR",
      },
    ],
    why: "We divide by good packets, not the expected count, because only good packets can be sold.",
    assertions: [17, 18, 19],
  },
  {
    id: "reports",
    nitStep: 9,
    title: "The month's reports",
    who: { role: "Auditor", login: "Auditor (read-only)" },
    screen: "reports",
    actions: [
      "Log in as the Auditor. Every screen is read-only.",
      "Reports → this month → Sales register, GST summary, Purchase register, Stock ledger, Production report, Receivables ageing.",
      "Click any row to open the document behind it. Export to CSV, Excel or PDF.",
    ],
    expect: [
      { label: "GST summary: CGST", key: "nit_expected.invoice_A.cgst", unit: "INR" },
      { label: "GST summary: SGST", key: "nit_expected.invoice_A.sgst", unit: "INR" },
      { label: "Every report row", text: "links to its source document" },
    ],
    why: "Month end becomes a download, not a week of copying numbers by hand.",
    assertions: [26],
  },
  {
    id: "finish",
    title: "Check everything in one click",
    who: { role: "Visitor", login: "No login needed" },
    screen: "judge",
    actions: [
      "Press Run NIT benchmark (Judge Mode), or run `make benchmark` in a terminal.",
      "It replays all nine steps on a separate demo copy and fills the scoreboard.",
      "Each row links to the record that proves it.",
    ],
    expect: [{ label: "Scoreboard", text: "every row green" }],
    why: "You can check the whole benchmark yourself in under a minute.",
    assertions: [],
  },
];

export function stepIndex(id: string | undefined): number {
  const i = STEPS.findIndex((s) => s.id === id);
  return i < 0 ? 0 : i;
}
