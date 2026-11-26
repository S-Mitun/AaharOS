import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import type { PublicPassport } from "./PassportPage";

const PASSPORT: PublicPassport = {
  demo: "DEMO: fictional factory and product, not for sale.",
  factory: "AaharOS Demo Snacks (DEMO)",
  fssai_no: "10000000000000 (DEMO)",
  product: "DEMO murukku 200g",
  lot_no: "B-001",
  made_on: "2026-11-21",
  best_before: "2027-02-19",
  past_best_before: false,
  net_quantity: "200 g",
  can_ask_for_more: true,
};
const SALESMAN = {
  user: { id: "u1", email: "s@aaharos-demo.invalid", display_name: "Salesman A (DEMO)" },
  organization: { id: "o1", code: "DEMO-FACTORY", name: "DEMO", kind: "LIVE" },
  role: "SALESMAN",
  permissions: ["order.read", "order.create", "customer.read"],
};

function serve(handlers: Record<string, () => Response>) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      calls.push(url);
      for (const [prefix, h] of Object.entries(handlers)) if (url.startsWith(prefix)) return h();
      return new Response(JSON.stringify({ error: { code: "unauthenticated" } }), {
        status: 401,
      });
    }),
  );
  return calls;
}
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
afterEach(() => vi.unstubAllGlobals());

describe("batch passport (MP13)", () => {
  it("opens without a login and shows the pack label facts only", async () => {
    serve({ "/api/public/passport/tok": () => json({ ...PASSPORT, can_ask_for_more: false }) });
    render(
      <MemoryRouter initialEntries={["/passport/tok"]}>
        <App />
      </MemoryRouter>,
    );
    expect(await screen.findByText("DEMO murukku 200g")).toBeInTheDocument();
    expect(screen.getByText("200 g")).toBeInTheDocument();
    expect(screen.getByText("10000000000000 (DEMO)")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("not for sale");
    expect(screen.queryByRole("button", { name: "Ask for more" })).not.toBeInTheDocument();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument(); // no app shell
  });

  it("hands the phone's share sheet a link for the salesman", async () => {
    serve({ "/api/public/passport/tok": () => json(PASSPORT) });
    const share = vi.fn(async () => undefined);
    Object.defineProperty(navigator, "share", { value: share, configurable: true });
    render(
      <MemoryRouter initialEntries={["/passport/tok"]}>
        <App />
      </MemoryRouter>,
    );
    await userEvent.click(await screen.findByRole("button", { name: "Ask for more" }));
    expect(share).toHaveBeenCalledWith({
      title: "Ask for more",
      text: expect.stringContaining("/sales/reorder/tok") as unknown as string,
    });
    Object.defineProperty(navigator, "share", { value: undefined, configurable: true });
  });

  it("says so when the passport link is not valid", async () => {
    serve({
      "/api/public/passport/": () =>
        json(
          { error: { code: "passport_not_found", message: "this passport link is not valid" } },
          404,
        ),
    });
    render(
      <MemoryRouter initialEntries={["/passport/forged"]}>
        <App />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("not valid");
  });

  it("takes the signed-in salesman from the link to the pre-filled order", async () => {
    serve({
      "/api/auth/me": () => json(SALESMAN),
      "/api/trace/reorder/tok": () =>
        json({ customer_id: "c1", order_path: "/sales/order/c1?repeat=1" }),
    });
    const { ReorderPage } = await import("./PassportPage");
    render(
      <MemoryRouter initialEntries={["/sales/reorder/tok"]}>
        <Routes>
          <Route path="/sales/reorder/:token" element={<ReorderPage />} />
          <Route path="/sales/order/:customerId" element={<p>order form for c1</p>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText("order form for c1")).toBeInTheDocument();
  });

  it("refuses a link for someone else's customer", async () => {
    serve({
      "/api/trace/reorder/tok": () =>
        json(
          {
            error: {
              code: "passport_not_found",
              message: "this reorder link is not for one of your customers",
            },
          },
          404,
        ),
    });
    const { ReorderPage } = await import("./PassportPage");
    render(
      <MemoryRouter initialEntries={["/sales/reorder/tok"]}>
        <Routes>
          <Route path="/sales/reorder/:token" element={<ReorderPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("not for one of your customers");
  });
});
