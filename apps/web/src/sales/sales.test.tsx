import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useRoutes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SessionProvider } from "../lib/session";
import { appRoutes } from "../routes";
import { OutboxProvider } from "./outbox";
import { MemoryStore } from "./sync";
import type { OutboxEntry, SendResult } from "./types";

const ME = {
  user: {
    id: "u-sales-a",
    email: "salesman.a@aaharos-demo.invalid",
    display_name: "Salesman A (DEMO)",
  },
  organization: {
    id: "o1",
    code: "DEMO-FACTORY",
    name: "AaharOS Demo Snacks (DEMO)",
    kind: "LIVE",
  },
  role: "SALESMAN",
  permissions: ["customer.read", "order.create", "order.read", "stock.read"],
};
const CUSTOMER = {
  id: "c-a",
  code: "RET-A",
  name: "DEMO Retailer A",
  kind: "RETAILER",
  state_code: "33",
  gstin: null,
  route_order: 1,
};
const CATALOG = {
  customer_id: "c-a",
  price_list: { id: "pl-1", code: "GENERAL", version: 1, effective_from: "2026-04-01" },
  products: [
    {
      item_id: "i-200",
      code: "murukku_200g",
      name: "DEMO murukku 200g",
      price_ex_tax: "50.00",
      units_per_carton: 20,
      available_today: "88",
    },
  ],
  note: "",
};
const SERVER_ORDER = {
  id: "o-1",
  order_no: "SO/26-27/000001",
  status: "SUBMITTED",
  captured_at: "2026-11-21T03:45:00+00:00",
  received_at: "2026-11-21T03:46:00+00:00",
  customer: { name: "DEMO Retailer A" },
  price_list: { code: "GENERAL", version: 1 },
  lines: [
    { item_name: "DEMO murukku 200g", qty: "100", price_ex_tax: "50.00", value_ex_tax: "5000.00" },
  ],
  total_ex_tax: {
    value: "5000.00",
    unit: "INR",
    formula: "Σ (packets x price ex-tax)",
    method: null,
    inputs: [],
  },
  stale: false,
  stale_detail: null,
  timeline: [{ to_status: "SUBMITTED", at: "2026-11-21T03:46:00+00:00", reason: null }],
};

function serve(lastOrder: unknown = null) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
      if (url === "/api/auth/me") return json(ME);
      if (url === "/api/customers") return json({ customers: [CUSTOMER] });
      if (url.startsWith("/api/sales/catalog")) return json(CATALOG);
      if (url.includes("/last-order")) return json({ last_order: lastOrder });
      if (url.startsWith("/api/orders?")) return json({ orders: [] });
      if (url === "/api/orders/o-1") return json(SERVER_ORDER);
      return json({ error: { code: "not_found", message: "no" } }, 404);
    }),
  );
}
afterEach(() => vi.unstubAllGlobals());

function Routes() {
  return useRoutes(appRoutes);
}

function renderSales(
  path: string,
  store: MemoryStore,
  send: (e: OutboxEntry) => Promise<SendResult>,
) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <SessionProvider>
        <OutboxProvider store={store} send={send} wipeStorage={() => Promise.resolve()}>
          <Routes />
        </OutboxProvider>
      </SessionProvider>
    </MemoryRouter>,
  );
}

describe("the salesman app", () => {
  it("saves to the phone first and says Received only after the factory's acknowledgement", async () => {
    serve();
    const store = new MemoryStore();
    const results: SendResult[] = [
      { kind: "network" },
      {
        kind: "ok",
        status: 201,
        order: { id: "o-1", order_no: "SO/26-27/000001", status: "SUBMITTED", stale: false },
      },
    ];
    const send = vi.fn(() => Promise.resolve(results.shift() ?? { kind: "network" as const }));
    const user = userEvent.setup();
    renderSales("/sales", store, send);

    expect(await screen.findByText("DEMO Retailer A")).toBeInTheDocument();
    await user.click(within(screen.getByRole("main")).getByRole("link", { name: "New order" }));
    expect(await screen.findByText(/In stock today \(88 available\)/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /One carton more/ }));
    expect(screen.getByRole("textbox", { name: /packets/ })).toHaveValue("20");
    await user.click(screen.getByRole("button", { name: /One packet more/ }));
    expect(screen.getByRole("textbox", { name: /packets/ })).toHaveValue("21");
    expect(screen.getByText("₹1,050.00")).toBeInTheDocument();

    await user.clear(screen.getByRole("textbox", { name: /packets/ }));
    await user.type(screen.getByRole("textbox", { name: /packets/ }), "100");
    expect(await screen.findByText(/Only 88 available today \(partial\)/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Save order" }));
    // the first send failed (no network): the order is on the phone, never "Received"
    await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
    expect(
      await screen.findByText("Saved on phone", { selector: ".chip *, .chip" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Received by factory/)).not.toBeInTheDocument();
    const [saved] = await store.all();
    expect(saved?.lines).toEqual([
      { itemId: "i-200", name: "DEMO murukku 200g", qty: "100", price: "50.00" },
    ]);

    // back online: it sends by itself, once more, with the same key
    await act(async () => {
      window.dispatchEvent(new Event("online"));
    });
    await waitFor(() => expect(send).toHaveBeenCalledTimes(2));
    const keys = (send.mock.calls as unknown as [OutboxEntry][]).map(([e]) => e.key);
    expect(keys).toEqual([saved?.key, saved?.key]);
    expect((await screen.findAllByText("SO/26-27/000001")).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Received by factory/).length).toBeGreaterThan(0);
  });

  it("repeats the last order with its quantities", async () => {
    serve({
      id: "o-0",
      order_no: "SO/26-27/000009",
      order_date: "2026-11-20",
      lines: [{ item_id: "i-200", qty: "150" }],
    });
    renderSales("/sales/order/c-a?repeat=1", new MemoryStore(), () =>
      Promise.resolve({ kind: "network" }),
    );
    await waitFor(() =>
      expect(screen.getByRole("textbox", { name: /packets/ })).toHaveValue("150"),
    );
    expect(screen.getByText("Last time: 150 packets")).toBeInTheDocument();
    expect(screen.getByText("₹7,500.00")).toBeInTheDocument();
  });

  it("shows a refused order under Needs attention with the server's reason", async () => {
    serve();
    const store = new MemoryStore();
    await store.put({
      localId: "l-1",
      key: "k-1",
      customerId: "c-a",
      customerName: "DEMO Retailer A",
      priceListId: "pl-1",
      priceListLabel: "GENERAL v1",
      lines: [{ itemId: "i-200", name: "DEMO murukku 200g", qty: "5", price: "1.00" }],
      capturedAt: "2026-11-21T04:00:00.000Z",
      state: "attention",
      attempts: 1,
      nextAttemptAt: 0,
      lastError: {
        status: 422,
        code: "price_mismatch",
        message: "the price sent does not match the factory's price list",
      },
    });
    renderSales("/sales/orders", store, () => Promise.resolve({ kind: "network" }));
    expect(
      await screen.findByRole("heading", { name: /Needs attention \(1\)/ }),
    ).toBeInTheDocument();
    expect(screen.getByText(/does not match the factory's price list/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Edit and send again" })).toHaveAttribute(
      "href",
      "/sales/order/c-a?edit=l-1",
    );
    await userEvent.setup().click(screen.getByRole("button", { name: "Discard" }));
    await waitFor(async () => expect(await store.all()).toEqual([]));
  });
});
