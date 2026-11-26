import { render, screen } from "@testing-library/react";
import { MemoryRouter, useRoutes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SessionProvider } from "../lib/session";
import { appRoutes } from "../routes";
import { OutboxProvider } from "../sales/outbox";
import { MemoryStore } from "../sales/sync";
import { expiresIn, type Freshness } from "./traceTypes";

const ME = {
  user: { id: "u-a", email: "salesman.a@aaharos-demo.invalid", display_name: "Salesman A (DEMO)" },
  organization: { id: "o1", code: "DEMO-FACTORY", name: "DEMO", kind: "LIVE" },
  role: "SALESMAN",
  permissions: ["customer.read", "order.create", "order.read", "stock.read"],
};
const CUSTOMER = {
  id: "c-d",
  code: "RET-D",
  name: "DEMO Retailer D",
  kind: "RETAILER",
  state_code: "33",
  route_order: 1,
};
const ex = (value: string, unit: string) => ({
  value,
  unit,
  formula: "test",
  method: null,
  inputs: [],
});
const FRESH: Freshness = {
  as_of: "2027-02-09",
  alert_days: "15",
  window_days: 90,
  flagged: 1,
  note: "An estimate from each customer's order rhythm over the last 90 days, not a shelf count.",
  rows: [
    {
      customer_id: "c-d",
      customer_code: "RET-D",
      customer_name: "DEMO Retailer D",
      item_code: "murukku_200g",
      item_name: "DEMO murukku 200g",
      lot_id: "l1",
      lot_no: "B-001",
      best_before: "2027-02-19",
      days_to_best_before: 10,
      delivered: ex("80", "packets"),
      low: "0",
      central: null,
      high: ex("80", "packets"),
      enough_history: false,
      rates: null,
      flagged: true,
      value_at_risk: ex("4000.00", "INR"),
    },
  ],
};

function serve(fresh: Freshness | null) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
      if (url === "/api/auth/me") return json(ME);
      if (url === "/api/customers") return json({ customers: [CUSTOMER] });
      if (url === "/api/trace/freshness")
        return fresh
          ? json(fresh)
          : json(
              {
                error: {
                  code: "setting_missing",
                  message: "the setting freshness.alert_days is not configured",
                },
              },
              422,
            );
      if (url.startsWith("/api/orders?")) return json({ orders: [] });
      return json({ error: { code: "not_found", message: "no" } }, 404);
    }),
  );
}
afterEach(() => vi.unstubAllGlobals());

function Routes() {
  return useRoutes(appRoutes);
}
const open = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <SessionProvider>
        <OutboxProvider
          store={new MemoryStore()}
          send={() => Promise.resolve({ kind: "network" })}
          wipeStorage={() => Promise.resolve()}
        >
          <Routes />
        </OutboxProvider>
      </SessionProvider>
    </MemoryRouter>,
  );

describe("the freshness radar in the salesman app (MP13)", () => {
  it("puts a chip on the customer in Today's list", async () => {
    serve(FRESH);
    open("/sales");
    expect(await screen.findByText("up to 80 packets expire in 10 days")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /up to 80 packets/ })).toHaveAttribute(
      "href",
      "/sales/freshness",
    );
  });

  it("lists what may be on each shelf, with the estimate's limits", async () => {
    serve(FRESH);
    open("/sales/freshness");
    expect(await screen.findByText("1 to visit soon")).toBeInTheDocument();
    expect(screen.getByText(/not enough order history/)).toBeInTheDocument();
    expect(screen.getByText("₹4,000.00")).toBeInTheDocument();
    expect(screen.getByText("80 expire in 10 days")).toBeInTheDocument();
  });

  it("explains a missing setting, and Today still works without chips", async () => {
    serve(null);
    open("/sales/freshness");
    expect(await screen.findByRole("alert")).toHaveTextContent("freshness.alert_days");
  });

  it("words the days left", () => {
    expect([expiresIn(null), expiresIn(-1), expiresIn(0), expiresIn(1), expiresIn(9)]).toEqual([
      "have no best-before date",
      "are past their best-before",
      "expire today",
      "expire in 1 day",
      "expire in 9 days",
    ]);
  });
});
