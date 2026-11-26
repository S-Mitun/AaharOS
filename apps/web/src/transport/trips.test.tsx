import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";

const me = (role: string, permissions: string[]) => ({
  user: { id: "u1", email: "x@aaharos-demo.invalid", display_name: `${role} (DEMO)` },
  organization: { id: "o1", code: "DEMO-FACTORY", name: "DEMO", kind: "LIVE" },
  role,
  permissions,
});
const ex = (value: string, unit: string, method: string | null = null) => ({
  value,
  unit,
  formula: "test",
  method,
  inputs: [],
});
const PLAN = {
  date: "2026-11-23",
  routing: "mock (straight line x road factor)",
  routes: [
    {
      vehicle: "DEMO mini truck",
      capacity_cartons: 40,
      cartons: 6,
      km: "191.231",
      cost: ex("1943.00", "INR"),
      co2: ex("38.2", "kg", "estimate (DEMO factor)"),
      stops: [
        {
          seq: 1,
          dispatch_no: "DSP/26-27/000003",
          invoice_no: "AHR/26-27/000003",
          customer: "DEMO Retailer A",
          packets: "30",
          cartons: "2",
          leg_km: "10.4",
          cost_share: "529.91",
        },
      ],
      return_km: "100.2",
      backhaul: [
        {
          supplier: "DEMO Flour Mills",
          detour_km: "1.2",
          text: "Pick up from DEMO Flour Mills on the way",
        },
      ],
    },
  ],
  unplanned: [
    {
      dispatch_no: "DSP/26-27/000009",
      customer: "DEMO Retailer Z",
      reason: "no location recorded for this customer",
    },
  ],
  note: "Distances are straight-line x the road factor.",
};
const TRIP = {
  id: "t1",
  trip_no: "TRP/26-27/000001",
  trip_date: "2026-11-23",
  status: "PLANNED",
  vehicle: "DEMO mini truck",
  planned_km: "191.231",
  actual_km: null,
  planned_cost: ex("1943.00", "INR"),
  actual_cost: null,
  co2: ex("38.2", "kg"),
  stops: [{ seq: 1, customer: "DEMO Retailer A", packets: "30", cost_share: "529.91" }],
};
const SERVE = {
  rows: [
    {
      customer_id: "c1",
      customer_name: "DEMO Retailer A",
      packets: "90",
      delivery: ex("1409.40", "INR"),
      credit: ex("46.60", "INR"),
      returns: ex("0", "INR"),
      total: ex("1456.00", "INR"),
      per_packet: ex("16.18", "INR/packet"),
      price_floor: ex("38.07", "INR/packet", "Deal Desk floor, ex tax"),
    },
  ],
};

function serve(who: unknown) {
  const posts: { url: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
      if (url === "/api/auth/me") return json(who);
      if (init?.method === "POST") {
        posts.push({ url, body: JSON.parse(String(init.body ?? "{}")) });
        return url.endsWith("/complete")
          ? json({ id: "t1", status: "DONE" })
          : json({ trips: ["TRP/26-27/000002"] }, 201);
      }
      if (url.startsWith("/api/transport/plan")) return json(PLAN);
      if (url.startsWith("/api/transport/trips")) return json({ trips: [TRIP] });
      if (url.startsWith("/api/transport/cost-to-serve")) return json(SERVE);
      return json({ error: { code: "not_found", message: "no" } }, 404);
    }),
  );
  return posts;
}
afterEach(() => vi.unstubAllGlobals());

const open = () =>
  render(
    <MemoryRouter initialEntries={["/admin/trips"]}>
      <App />
    </MemoryRouter>,
  );

describe("Trips and cost-to-serve (MP14)", () => {
  it("shows the plan, the unplanned reason, backhaul and the Deal Desk floor", async () => {
    serve(me("ADMIN", ["report.read", "dispatch.post"]));
    open();
    expect(await screen.findByText(/6 of 40 cartons/)).toBeInTheDocument();
    expect(screen.getByText("Pick up from DEMO Flour Mills on the way")).toBeInTheDocument();
    expect(screen.getByText(/no location recorded for this customer/)).toBeInTheDocument();
    expect(await screen.findByText("₹38.07 / packet")).toBeInTheDocument();
  });

  it("creates the trips and records the actual km", async () => {
    const posts = serve(me("ADMIN", ["report.read", "dispatch.post"]));
    open();
    await userEvent.click(await screen.findByRole("button", { name: "Create these trips" }));
    await waitFor(() => expect(posts[0]?.url).toBe("/api/transport/trips"));
    await userEvent.type(screen.getByLabelText("actual km of TRP/26-27/000001"), "199");
    await userEvent.click(screen.getByRole("button", { name: "Record" }));
    await waitFor(() =>
      expect(posts[1]).toEqual({
        url: "/api/transport/trips/t1/complete",
        body: { actual_km: "199", tolls: "0" },
      }),
    );
  });

  it("is read-only without dispatch permission", async () => {
    serve(me("AUDITOR", ["report.read"]));
    open();
    expect(await screen.findByText(/6 of 40 cartons/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create these trips" })).not.toBeInTheDocument();
    expect(screen.getByText("not back yet")).toBeInTheDocument();
  });
});
