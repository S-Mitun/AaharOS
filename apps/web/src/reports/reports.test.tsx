import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";

const AUDITOR = {
  user: { id: "u-aud", email: "auditor@aaharos-demo.invalid", display_name: "Auditor (DEMO)" },
  organization: {
    id: "o1",
    code: "DEMO-FACTORY",
    name: "AaharOS Demo Snacks (DEMO)",
    kind: "LIVE",
  },
  role: "AUDITOR",
  permissions: ["customer.read", "order.read", "stock.read", "report.read", "audit.read"],
};

const SALES = {
  name: "sales-register",
  title: "Sales register",
  organization: "AaharOS Demo Snacks (DEMO)",
  filters: { from: "2026-11-01", to: "2026-11-21" },
  generated_at: "2026-11-21T10:00:00+05:30",
  columns: [
    { key: "doc_no", label: "Document", kind: "text" },
    { key: "taxable", label: "Taxable", kind: "money" },
    { key: "total", label: "Total", kind: "money" },
  ],
  rows: [
    {
      doc_no: "AHR/26-27/000001",
      taxable: "7500.00",
      total: "7875.00",
      _source: { type: "invoice", id: "inv-1" },
    },
  ],
  totals: { taxable: "7500.00", total: "7875.00" },
  notes: ["Totals count POSTED invoices."],
};

const COCKPIT = {
  organization: "AaharOS Demo Snacks (DEMO)",
  month: "2026-11-01",
  locked: false,
  checklist: [
    {
      key: "orders_to_decide",
      label: "Orders waiting for a decision",
      count: 1,
      ok: false,
      link: "/admin/orders",
    },
  ],
  integrity: [
    { check: "Law 3 mass: every batch reconciles, gaps disclosed", ok: true, problems: 0 },
    { check: "Law 4 tax: invoice tax lines = GST summary = export", ok: true, problems: 0 },
  ],
  can_close: true,
  history: [],
};

function serve() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });
      if (url === "/api/auth/me") return json(AUDITOR);
      if (url === "/api/reports")
        return json({ reports: [{ name: "sales-register", title: "Sales register" }] });
      if (url.startsWith("/api/reports/sales-register")) return json(SALES);
      if (url.startsWith("/api/reports/close")) return json(COCKPIT);
      return json({ error: { code: "not_found" } });
    }),
  );
}
afterEach(() => vi.unstubAllGlobals());

describe("Reports (MP11)", () => {
  it("shows a report with exact totals, drill-down and downloads", async () => {
    serve();
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/auditor/reports"]}>
        <App />
      </MemoryRouter>,
    );
    await user.click(await screen.findByRole("button", { name: "Show" }));
    expect(await screen.findByText("AHR/26-27/000001")).toBeInTheDocument();
    expect(screen.getAllByText("₹7,875.00")).toHaveLength(2); // the row and the total
    expect(screen.getByRole("link", { name: "Open" })).toHaveAttribute(
      "href",
      "/admin/invoices/inv-1",
    );
    expect(screen.getByRole("link", { name: "Excel" }).getAttribute("href")).toContain(
      "format=xlsx",
    );
  });

  it("lets an auditor see the close cockpit but not close the month", async () => {
    serve();
    render(
      <MemoryRouter initialEntries={["/auditor/reports?tab=close"]}>
        <App />
      </MemoryRouter>,
    );
    expect(
      await screen.findByRole("link", { name: "Orders waiting for a decision" }),
    ).toHaveAttribute("href", "/admin/orders");
    expect(screen.getByText(/Law 4 tax/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Close the month" })).not.toBeInTheDocument();
  });
});
