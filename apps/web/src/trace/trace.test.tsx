import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import type { Batch, LotRow, Recall, Trace } from "./traceTypes";

const me = (role: string, permissions: string[]) => ({
  user: { id: "u1", email: "x@aaharos-demo.invalid", display_name: `${role} (DEMO)` },
  organization: {
    id: "o1",
    code: "DEMO-FACTORY",
    name: "AaharOS Demo Snacks (DEMO)",
    kind: "LIVE",
  },
  role,
  permissions,
});
const PRODUCTION = me("PRODUCTION", ["report.read", "run.start", "stock.read"]);
const NO_REPORTS = me("ADMIN", ["order.approve"]); // a role without report.read
const ex = (value: string, unit: string, formula = "test") => ({
  value,
  unit,
  formula,
  method: null,
  inputs: [],
});

const LOT: LotRow = {
  lot_id: "lot-b2",
  lot_no: "B-002",
  kind: "batch_lot",
  kind_label: "Batch",
  item_id: "i1",
  item_code: "murukku_200g",
  item_name: "DEMO murukku 200g",
  mfg_date: "2026-11-17",
  best_before: "2027-02-15",
};
const BATCH: Batch = {
  run_id: "r2",
  run_no: "B-002",
  status: "COMPLETED",
  run_date: "2026-11-17",
  completed_at: null,
  recipe: { code: "MURUKKU", version: 1, version_id: "rv" },
  packs: [{ code: "MURUKKU-200G", version: 1, version_id: "pv" }],
  operator: "DEMO Production",
  lots: [{ lot_id: "lot-b2", lot_no: "B-002", pack_code: "MURUKKU-200G", good_units: 180 }],
};
const TRACE: Trace = {
  lot: LOT,
  note: "may contain",
  backward: {
    batch: BATCH,
    materials: [
      {
        item_code: "flour",
        store: "RAW_STORE",
        document: "MI/26-27/000002",
        direction: "ISSUE",
        posting_date: "2026-11-17",
        qty: ex("30", "kg"),
        source: { type: "material_issue", id: "mi2" },
        may_contain: [
          {
            kind: "supplier_lot",
            label: "supplier lot FL-B (DEMO Flour Mills)",
            date: "2026-11-17",
            lot_no: "FL-B",
            source: { type: "purchase_receipt", id: "rc2" },
          },
        ],
      },
    ],
  },
  forward: [
    {
      ...LOT,
      made: ex("180", "packets"),
      dispatched: ex("60", "packets"),
      on_hand: ex("120", "packets"),
      dispatches: [
        {
          dispatch_id: "d2",
          dispatch_no: "DSP/26-27/000002",
          dispatch_date: "2026-11-20",
          invoice_id: "inv2",
          invoice_no: "AHR/26-27/000002",
          customer_id: "c2",
          customer_code: "DIST-B",
          customer_name: "DEMO Distributor B",
          packets: "60",
        },
      ],
    },
  ],
};
const RECALL: Recall = {
  simulation: true,
  note: "DEMO simulation: nothing is stored and nothing is sent.",
  may_contain_note: null,
  subject: "batch lot B-002 of murukku_200g",
  lot: LOT,
  batches: [BATCH],
  lots: TRACE.forward,
  customers: [
    {
      customer_id: "c2",
      customer_code: "DIST-B",
      customer_name: "DEMO Distributor B",
      packets: ex("60", "packets"),
      invoice_nos: ["AHR/26-27/000002"],
      lot_nos: ["B-002"],
      last_dispatch: "2026-11-20",
    },
  ],
  totals: {
    made: ex("180", "packets"),
    dispatched: ex("60", "packets"),
    on_hand: ex("120", "packets"),
    customers: "1",
  },
  notice: "DEMO SIMULATION - NOTHING HAS BEEN SENT.\nDRAFT PRODUCT RECALL NOTICE",
};

function serve(who: unknown, failTrace = false) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      calls.push(url);
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
      if (url === "/api/auth/me") return json(who);
      if (url.startsWith("/api/trace/lots?")) return json({ lots: [LOT] });
      if (url === "/api/trace/lots/lot-b2")
        return failTrace
          ? json({ error: { code: "lot_not_found", message: "unknown lot" } }, 404)
          : json(TRACE);
      if (url.startsWith("/api/trace/recall/lot-b2")) return json(RECALL);
      if (url === "/api/trace/passport/lot-b2")
        return json({
          token: "tok",
          path: "/passport/tok",
          url: "http://x/passport/tok",
          qr_svg: "<svg></svg>",
        });
      return json({ error: { code: "not_found", message: "no" } }, 404);
    }),
  );
  return calls;
}
afterEach(() => vi.unstubAllGlobals());

const open = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );

describe("Trace and recall (MP13)", () => {
  it("traces a batch back to its supplier lots and forward to the invoice", async () => {
    serve(PRODUCTION);
    open("/production/trace");
    await userEvent.click(await screen.findByRole("button", { name: /B-002 Batch/ }));
    expect(await screen.findByRole("heading", { name: "Batch B-002" })).toBeInTheDocument();
    expect(screen.getByText(/Recipe MURUKKU v1 · Pack MURUKKU-200G v1/)).toBeInTheDocument();
    expect(screen.getByText("supplier lot FL-B (DEMO Flour Mills)")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "AHR/26-27/000002" })).toHaveAttribute(
      "href",
      "/admin/invoices/inv2",
    );
    expect(screen.getByText("120 packets")).toBeInTheDocument();
    expect(await screen.findByAltText("QR code for the passport of lot B-002")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open the passport" })).toHaveAttribute(
      "href",
      "/passport/tok",
    );
  });

  it("simulates a recall with a DEMO banner and the reason in the request", async () => {
    const calls = serve(PRODUCTION);
    open("/production/trace?lot=lot-b2");
    await screen.findByRole("heading", { name: "Batch B-002" });
    await userEvent.type(screen.getByLabelText(/Reason/), "DEMO: oil smell");
    await userEvent.click(screen.getByRole("button", { name: "Simulate recall" }));
    const sim = await screen.findByLabelText("Recall simulation");
    expect(within(sim).getByRole("note")).toHaveTextContent("nothing is sent");
    expect(within(sim).getByText("DEMO Distributor B")).toBeInTheDocument();
    expect(within(sim).getByText(/DRAFT PRODUCT RECALL NOTICE/)).toBeInTheDocument();
    await waitFor(() =>
      expect(calls).toContain("/api/trace/recall/lot-b2?reason=DEMO%3A%20oil%20smell"),
    );
  });

  it("says so when the lot cannot be traced", async () => {
    serve(PRODUCTION, true);
    open("/production/trace?lot=lot-b2");
    expect(await screen.findByRole("alert")).toHaveTextContent("unknown lot");
  });

  it("is not part of a role without report.read", async () => {
    serve(NO_REPORTS);
    open("/production/trace");
    expect(
      await screen.findByRole("heading", { name: "Not part of your role" }),
    ).toBeInTheDocument();
  });
});
