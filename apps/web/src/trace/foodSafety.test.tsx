import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import type { FillWeights, OilLog } from "./traceTypes";

const PRODUCTION = {
  user: { id: "u1", email: "x@aaharos-demo.invalid", display_name: "PRODUCTION (DEMO)" },
  organization: { id: "o1", code: "DEMO-FACTORY", name: "DEMO", kind: "LIVE" },
  role: "PRODUCTION",
  permissions: ["report.read", "run.start"],
};
const ex = (value: string, unit: string) => ({
  value,
  unit,
  formula: "test",
  method: null,
  inputs: [],
});

const OIL: OilLog = {
  date_from: "2026-10-28",
  date_to: "2026-11-26",
  threshold_l_per_day: "50",
  tpc_limit_pct: "25",
  records_required: true,
  days: [
    {
      date: "2026-11-25",
      litres: ex("55", "L"),
      above_threshold: true,
      sessions: [
        {
          run_id: "r3",
          run_no: "B-003",
          fresh_l: "50",
          topup_l: "5",
          discard_l: "1.5",
          tpc_pct: "26",
          discard_oil: true,
        },
      ],
    },
  ],
  note: "DEMO settings",
};
const FILL: FillWeights = {
  date_from: "2026-10-28",
  date_to: "2026-11-26",
  tolerances: [{ declared_g: "200", tolerance_g: "9" }],
  runs: [
    {
      run_id: "r3",
      run_no: "B-003",
      run_date: "2026-11-25",
      pack_code: "MURUKKU-200G",
      declared_g: "200",
      good_units: "192",
      samples: ["199", "190"],
      mean_net: ex("194.5", "g"),
      over_per_packet: ex("-5.5", "g"),
      cost_per_kg: ex("85.75", "INR/kg"),
      giveaway: ex("0.00", "INR"),
      tolerance_g: "9",
      short_limit_g: "191",
      short_samples: ["190"],
      short_fill_alert: true,
    },
  ],
  note: "DEMO values: verify the tolerance table with a Legal Metrology officer before real use.",
};

function serve(oilFails = false) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
      if (url === "/api/auth/me") return json(PRODUCTION);
      if (url.startsWith("/api/trace/oil"))
        return oilFails
          ? json(
              {
                error: {
                  code: "setting_missing",
                  message: "the setting fssai.tpc_limit_pct is not configured",
                },
              },
              422,
            )
          : json(OIL);
      if (url.startsWith("/api/trace/fill-weights")) return json(FILL);
      return json({ error: { code: "not_found", message: "no" } }, 404);
    }),
  );
}
afterEach(() => vi.unstubAllGlobals());

const open = () =>
  render(
    <MemoryRouter initialEntries={["/production/food-safety"]}>
      <App />
    </MemoryRouter>,
  );

describe("Oil and fill weights (MP13)", () => {
  it("flags days above the RUCO threshold, oil to discard and short fills", async () => {
    serve();
    open();
    expect(await screen.findByText("daily used-oil records required")).toBeInTheDocument();
    expect(screen.getByText("55 L")).toBeInTheDocument();
    expect(screen.getByText("discard")).toBeInTheDocument();
    const fill = screen.getByRole("heading", { name: "Fill weights" }).nextElementSibling!;
    expect(fill).toHaveTextContent("200 g → 9 g");
    expect(fill).toHaveTextContent("Legal Metrology");
    const row = screen.getByRole("row", { name: /B-003 2026-11-25/ });
    expect(within(row).getByText("1 below 191 g")).toBeInTheDocument();
    expect(within(row).getByText("₹0.00")).toBeInTheDocument();
  });

  it("says which setting is missing instead of showing numbers", async () => {
    serve(true);
    open();
    expect(await screen.findByRole("alert")).toHaveTextContent("fssai.tpc_limit_pct");
    expect(await screen.findByText(/1 below 191 g/)).toBeInTheDocument(); // fill weights still load
  });
});
