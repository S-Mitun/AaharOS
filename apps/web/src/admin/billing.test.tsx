import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import type { DispatchPreview, InvoiceView } from "./billingTypes";

const ADMIN = {
  user: {
    id: "u-admin",
    email: "admin@aaharos-demo.invalid",
    display_name: "Factory Admin (DEMO)",
  },
  organization: {
    id: "o1",
    code: "DEMO-FACTORY",
    name: "AaharOS Demo Snacks (DEMO)",
    kind: "LIVE",
  },
  role: "ADMIN",
  permissions: [
    "order.approve",
    "invoice.post",
    "invoice.cancel",
    "dispatch.post",
    "payment.post",
    "report.read",
    "credit_note.post",
  ],
};

/** NIT's invoice A as the API returns it. */
const INVOICE: InvoiceView = {
  id: "inv-1",
  invoice_no: "AHR/26-27/000001",
  invoice_date: "2026-11-21",
  due_date: "2026-12-21",
  status: "POSTED",
  cancel_reason: null,
  order_id: "o-a",
  order_no: "SO/26-27/000001",
  regime: "INTRA",
  place_of_supply: "33-Tamil Nadu",
  supplier: { name: "AaharOS Demo Snacks (DEMO)", state_label: "33-Tamil Nadu" },
  customer: {
    id: "c-a",
    name: "DEMO Retailer A",
    gstin: "33DEMOA0000A1Z0",
    state_label: "33-Tamil Nadu",
  },
  lines: [
    {
      line_no: 1,
      item_id: "i-200",
      item_name: "DEMO murukku 200g",
      hsn: "21069099",
      qty: "150",
      unit: "packet",
      rate: "50.00",
      taxable: "7500.00",
      dispatched: "0",
      taxes: [
        { tax: "CGST", rate_pct: "2.5", amount: "187.50" },
        { tax: "SGST", rate_pct: "2.5", amount: "187.50" },
      ],
    },
  ],
  taxable: "7500.00",
  by_tax: { CGST: "187.50", SGST: "187.50" },
  round_off: "0.00",
  total: "7875.00",
  amount_in_words: "Rupees Seven Thousand Eight Hundred Seventy Five Only",
  lots: [],
  paid: "0.00",
  credited: "0.00",
  outstanding: "7875.00",
  credit_notes: [],
};
const PREVIEW: DispatchPreview = {
  invoice_no: "AHR/26-27/000001",
  dispatch_date: "2026-11-21",
  lines: [
    {
      item_id: "i-200",
      item_name: "DEMO murukku 200g",
      invoiced: "150",
      already_dispatched: "0",
      now: "150",
      fefo: true,
      picks: [
        { lot_no: "OPEN-LOT", qty: "50", value: "1442.50" },
        { lot_no: "B-001", qty: "100", value: "2156.91" },
      ],
      stock_movement: [],
    },
  ],
  cost_of_goods: "3599.41",
  consignment_value: "7875.00",
  eway: {
    required: false,
    reason:
      "Not required: intra-state consignment value 7875.00 is not above the 50000.00 threshold (Rule 138)",
    threshold: "50000.00",
    mock: true,
  },
};

function serve() {
  const posts: string[] = [];
  let dispatched = false;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
      if (url === "/api/auth/me") return json(ADMIN);
      if (init?.method === "POST") posts.push(url);
      if (url.endsWith("/dispatch-preview")) return json(PREVIEW);
      if (url.endsWith("/dispatch") && init?.method === "POST") {
        dispatched = true;
        return json({
          id: "d-1",
          dispatch_no: "DSP/26-27/000001",
          dispatch_date: "2026-11-21",
          eway: { required: false, reason: null, mock: true },
          lines: [],
        });
      }
      if (url.endsWith("/dispatches")) return json({ dispatches: [] });
      if (url === "/api/invoices/inv-1")
        return json(
          dispatched
            ? { ...INVOICE, lines: [{ ...INVOICE.lines[0]!, dispatched: "150" }] }
            : INVOICE,
        );
      return json({ error: { code: "not_found", message: "no" } }, 404);
    }),
  );
  return posts;
}
afterEach(() => vi.unstubAllGlobals());

describe("an invoice (MP10)", () => {
  it("shows NIT's tax breakup, previews the FEFO dispatch, then records it", async () => {
    const posts = serve();
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/admin/invoices/inv-1"]}>
        <App />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("heading", { name: /AHR\/26-27\/000001/ })).toBeInTheDocument();
    expect(screen.getAllByText("₹187.50")).toHaveLength(2);
    expect(screen.getAllByText("₹7,875.00").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /Open printable invoice/ })).toHaveAttribute(
      "href",
      "/api/invoices/inv-1/document",
    );
    await user.click(screen.getByRole("button", { name: "Preview the dispatch of 150 packets" }));
    expect(await screen.findByText("OPEN-LOT")).toBeInTheDocument();
    expect(screen.getByText("B-001")).toBeInTheDocument();
    expect(screen.getByText("e-Way Bill not required")).toBeInTheDocument();
    expect(posts).toEqual(["/api/invoices/inv-1/dispatch-preview"]); // nothing posted yet
    await user.click(screen.getByRole("button", { name: "Record dispatch" }));
    expect(await screen.findByText(/Dispatched as DSP\/26-27\/000001/)).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: /Preview the dispatch/ }),
      ).not.toBeInTheDocument(),
    );
  });
});
