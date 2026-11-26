import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import type { BatchPlan, Brief, RunwayPack } from "./planningTypes";

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
const OWNER = me("OWNER", ["report.read", "run.start", "receipt.post", "order.approve"]);
const AUDITOR = me("AUDITOR", ["report.read", "order.read", "stock.read"]);
const ex = (value: string, unit = "INR", formula = "test") => ({
  value,
  unit,
  formula,
  method: null,
  inputs: [],
});

const BRIEF: Brief = {
  date: "2026-11-26",
  cards: {
    orders: {
      today: { count: 2, value: "13500.00" },
      to_decide: { count: 1, value: "7500.00" },
      link: "/admin/orders",
    },
    available_vs_pending: {
      items: [
        {
          item_code: "murukku_200g",
          open_packets: "32",
          available: "0",
          shortfall: "32",
          value_per_packet: "50.00",
          met_today: "32",
        },
      ],
      note: null,
      link: "/production/planner",
    },
    leaks: {
      top: [
        {
          run_id: "r1",
          run_no: "B-001",
          label: "Yield loss",
          value: ex("258.81"),
          link: "/leaks/r1",
        },
      ],
      link: "/leaks",
    },
    runway: {
      packs: [
        { pack_code: "MURUKKU-200G", binding: ["pouch_200g"], full_batches: ex("1", "batches") },
      ],
      link: "/production/planner",
    },
    money: {
      outstanding: "3875.00",
      overdue: ex("0.00"),
      past_msme_45_days: "0.00",
      top_overdue: [],
      link: "/admin/collections",
    },
  },
  actions: [
    {
      kind: "decide",
      title: "Decide 1 waiting order",
      impact: ex("7500.00"),
      link: "/admin/orders",
    },
    {
      kind: "make",
      title: "Start 1 batch of MURUKKU-200G today",
      impact: ex("1600.00"),
      link: "/production/planner",
    },
  ],
};

const RUNWAY: RunwayPack[] = [
  {
    pack_code: "MURUKKU-200G",
    pack_name: "DEMO murukku 200g",
    recipe: "MURUKKU v1",
    expected_good_per_batch: "200",
    materials: [
      {
        item_code: "cooking_oil",
        unit: "L",
        available: "19.5",
        per_batch: "10",
        batches: ex("1.95", "batches"),
        binding: false,
      },
      {
        item_code: "pouch_200g",
        unit: "piece",
        available: "306",
        per_batch: "200",
        batches: ex("1.53", "batches"),
        binding: true,
      },
    ],
    binding: ["pouch_200g"],
    full_batches: ex("1", "batches"),
  },
];

const PLAN: BatchPlan = {
  date: "2026-11-26",
  capacity: "2",
  status: "OPTIMAL",
  demand: BRIEF.cards.available_vs_pending.items,
  batches: [
    {
      pack_code: "MURUKKU-200G",
      pack_version_id: "pv1",
      recipe_version_id: "rv1",
      batches: ex("1", "batches"),
      good_packets_per_batch: "200",
    },
  ],
  value_met: "1600.00",
  materials_used: [],
  materials_short: [],
  purchases: [
    {
      item_code: "pouch_200g",
      item_id: "i-pouch",
      qty: "500",
      unit: "piece",
      qty_base: "500",
      needed_by: "2026-12-03",
      lead_time_days: 7,
      explained: ex("500", "base units"),
    },
  ],
  note: "A recommendation.",
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
        return url.endsWith("/batches")
          ? json({ run_id: "run-9", status: "DRAFT" }, 201)
          : json({ id: "d1", draft_no: "DPO/2026-27/000001", status: "DRAFT" }, 201);
      }
      if (url === "/api/planning/brief") return json(BRIEF);
      if (url === "/api/planning/runway") return json({ packs: RUNWAY });
      if (url === "/api/planning/plan") return json(PLAN);
      if (url === "/api/planning/purchase-drafts") return json({ drafts: [] });
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

const CARDS = [
  "Today’s orders",
  "Available vs pending",
  "Where profit leaks",
  "Material runway",
  "Money to collect",
];

describe("the owner's morning brief (MP12)", () => {
  it("shows five cards and the actions in the server's order, each explainable", async () => {
    serve(OWNER);
    renderAt("/owner");
    expect(await screen.findByRole("heading", { name: "Today’s 3 actions" })).toBeInTheDocument();
    const actions = [...document.querySelectorAll<HTMLElement>(".action-item")];
    expect(actions.map((a) => a.querySelector(".action-title")?.textContent)).toEqual([
      "Decide 1 waiting order",
      "Start 1 batch of Murukku 200 g today",
    ]);
    expect(
      within(actions[0]!).getByRole("button", { name: /Explain this number/ }),
    ).toBeInTheDocument();
    for (const card of CARDS)
      expect(screen.getByRole("heading", { name: card })).toBeInTheDocument();
    expect(document.querySelectorAll(".brief-card")).toHaveLength(5);
    expect(screen.getByText(/32 short/)).toBeInTheDocument();
  });
});

describe("the batch planner (MP12)", () => {
  it("marks the binding material and creates drafts only", async () => {
    const posts = serve(OWNER);
    const user = userEvent.setup();
    renderAt("/production/planner");
    const [pouch] = await screen.findAllByRole("row", { name: /pouch 200g.*runs out first/ });
    expect(within(pouch!).getByText(/^1.53/)).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Create draft batch" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]).toEqual({
      url: "/api/planning/batches",
      body: { recipe_version_id: "rv1", pack_version_id: "pv1", batches: 1 },
    });
    expect(await screen.findByText(/Draft batch of MURUKKU-200G created/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create draft purchase order" }));
    await waitFor(() => expect(posts).toHaveLength(2));
    expect(posts[1]!.url).toBe("/api/planning/purchase-drafts");
    expect(await screen.findByText(/DPO\/2026-27\/000001 created/)).toBeInTheDocument();
  });

  it("is read-only for the auditor: no approve buttons", async () => {
    serve(AUDITOR);
    renderAt("/production/planner");
    expect(await screen.findAllByRole("row", { name: /pouch 200g/ })).toHaveLength(2);
    expect(screen.queryByRole("button", { name: /Create draft/ })).not.toBeInTheDocument();
  });
});
