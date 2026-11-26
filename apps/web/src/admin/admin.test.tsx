import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import type { OrderCard } from "./types";

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
    "customer.read",
    "order.read",
    "order.approve",
    "order.amend",
    "price.manage",
    "stock.read",
  ],
};
const ex = (value: string, formula: string, unit = "packets") => ({
  value,
  unit,
  formula,
  method: null,
  inputs: [],
});

/** Distributor B after Retailer A's approval, as the API returns it (NIT step 6). */
const B_CARD: OrderCard = {
  id: "o-b",
  order_no: "SO/26-27/000002",
  order_date: "2026-11-21",
  status: "SUBMITTED",
  captured_at: "2026-11-21T04:00:00+00:00",
  received_at: "2026-11-21T04:01:00+00:00",
  customer: {
    id: "c-b",
    code: "DIST-B",
    name: "DEMO Distributor B",
    kind: "DISTRIBUTOR",
    state_code: "29",
  },
  salesman: { id: "u-b", name: "Salesman B (DEMO)" },
  price_list: { code: "GENERAL", version: 1 },
  stale: false,
  stale_detail: null,
  timeline: [
    { from_status: null, to_status: "SUBMITTED", at: "2026-11-21T04:01:00+00:00", reason: null },
  ],
  card_lines: [
    {
      line_no: 1,
      item_id: "i-200",
      item_code: "murukku_200g",
      item_name: "DEMO murukku 200g",
      requested: "120",
      approved: "0",
      backordered: "0",
      open: "120",
      price_captured: "50.00",
      price_final: null,
      amend_reason: null,
      price_current: "50.00",
      available: ex("88", "on hand - reserved"),
      shortage: ex("32", "max(0, packets to decide - available to promise)"),
      can_send_now: "88",
      next_batch: null,
    },
  ],
  shortage_total: "32",
  credit: {
    limit: "100000.00",
    outstanding: ex("0.00", "no invoices exist until MP10", "INR"),
    exposure: ex("6000.00", "outstanding + this order (ex-tax)", "INR"),
    over_limit: false,
  },
  stale_choice_needed: false,
  waiting: false,
  actions: ["amend_price", "approve", "reject", "wait"],
};

function serve(card: OrderCard = B_CARD) {
  const posts: { url: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
      if (url === "/api/auth/me") return json(ADMIN);
      if (url.startsWith("/api/inbox?"))
        return json({
          view: "to_decide",
          orders: [
            {
              id: "o-b",
              order_no: "SO/26-27/000002",
              order_date: "2026-11-21",
              received_at: "",
              status: "SUBMITTED",
              customer_name: "DEMO Distributor B",
              packets: "120",
              value_ex_tax: "6000.00",
              short: true,
              stale: false,
              waiting: false,
            },
          ],
        });
      if (url === "/api/inbox/o-b") return json(card);
      if (url === "/api/planning/shortage/o-b")
        return json({
          order_id: "o-b",
          order_no: "SO/26-27/000002",
          lines: [
            {
              item_id: "i-mur",
              item_name: "DEMO murukku 200g",
              shortage: 32,
              attributed_to_yield_loss: ex("12", "min(shortage, expected - good)"),
              would_have_been: 20,
            },
          ],
        });
      if (init?.method === "POST") {
        posts.push({ url, body: JSON.parse(String(init.body ?? "{}")) });
        return json({
          ...card,
          status: "PART_APPROVED",
          card_lines: [{ ...card.card_lines[0]!, approved: "88", backordered: "32", open: "32" }],
          actions: ["amend_price", "amend_qty", "approve_backorder", "cancel", "reject"],
          decision: { status: "PART_APPROVED", summary: "approved 88 packets, 32 backordered" },
        });
      }
      return json({ error: { code: "not_found", message: "no" } }, 404);
    }),
  );
  return posts;
}
afterEach(() => vi.unstubAllGlobals());

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );

describe("the order inbox (MP09)", () => {
  it("lists orders with plain flags", async () => {
    serve();
    renderAt("/admin/orders");
    expect(await screen.findByText("DEMO Distributor B")).toBeInTheDocument();
    expect(screen.getByText("Short of stock")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "To decide" })).toHaveAttribute("aria-selected", "true");
  });

  it("shows Distributor B's shortage and the three options, then sends 88 and backorders 32", async () => {
    const posts = serve();
    const user = userEvent.setup();
    renderAt("/admin/orders/o-b");
    expect(await screen.findByRole("heading", { name: "DEMO Distributor B" })).toBeInTheDocument();
    const row = screen.getByRole("row", { name: /DEMO murukku 200g/ });
    expect(within(row).getByText("120")).toBeInTheDocument();
    expect(within(row).getByText(/^88 packets/)).toBeInTheDocument();
    expect(within(row).getByText(/^32 packets/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Approve all/ })).not.toBeInTheDocument();
    expect(screen.getByText(/No batch is planned yet/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject the order" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Send 88 now, backorder 32" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]).toEqual({ url: "/api/orders/o-b/approve", body: { partial: true } });
    expect(await screen.findByText(/approved 88 packets, 32 backordered/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Fill the backorder/ })).toBeInTheDocument();
    // MP12, row 23: 12 of the 32 short packets come from the batch's lost packets
    expect(await screen.findByText(/Why short\?/)).toBeInTheDocument();
    expect(screen.getByText(/the shortage would have been 20/)).toBeInTheDocument();
  });

  it("asks which price applies when the price list changed while the phone was offline", async () => {
    serve({
      ...B_CARD,
      shortage_total: "0",
      stale: true,
      stale_choice_needed: true,
      card_lines: [
        {
          ...B_CARD.card_lines[0]!,
          price_current: "52.00",
          shortage: ex("0", "x"),
          available: ex("238", "on hand - reserved"),
        },
      ],
    });
    const user = userEvent.setup();
    renderAt("/admin/orders/o-b");
    const approve = await screen.findByRole("button", { name: "Approve all 120 packets" });
    expect(approve).toBeDisabled();
    await user.click(screen.getByLabelText(/Today's list price \(₹52.00\)/));
    expect(approve).toBeEnabled();
  });
});
