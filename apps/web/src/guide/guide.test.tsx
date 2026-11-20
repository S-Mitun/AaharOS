import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { parse } from "yaml";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { fillTemplate, formatValue, lookup, placeholders } from "../lib/format";
import { NIT_CHECKS } from "./checks";
import { SCREENS } from "./screens";
import { STEPS } from "./steps";

// The real oracle, parsed with every scalar as a string (like the API, which never sends floats).
const oracleFile = resolve(__dirname, "../../../../benchmark/expected_results.yaml");
const raw = parse(readFileSync(oracleFile, "utf8"), { schema: "failsafe" }) as Record<
  string,
  unknown
>;
const payload = {
  config: {
    timezone: raw.timezone,
    factory_state: raw.factory_state,
    gst_rate_percent: raw.gst_rate_percent,
    variance_tolerance_percent: raw.variance_tolerance_percent,
  },
  inputs: raw.inputs,
  nit_expected: raw.nit_expected,
  aaharos_expected: raw.aaharos_expected,
  assumptions: raw.assumptions,
};

describe("guide content is bound to the oracle", () => {
  it("has the intro, NIT's nine steps in order, and a finish card", () => {
    expect(STEPS).toHaveLength(11);
    expect(STEPS.filter((s) => s.nitStep).map((s) => s.nitStep)).toEqual([
      1, 2, 3, 4, 5, 6, 7, 8, 9,
    ]);
  });

  it.each(STEPS.map((s) => [s.id, s] as const))(
    "step %s: every value resolves in the oracle",
    (_, step) => {
      expect(SCREENS[step.screen]).toBeDefined();
      for (const item of step.expect) {
        if ("key" in item) expect(lookup(payload, item.key), item.key).toBeDefined();
      }
      for (const text of step.actions) {
        for (const key of placeholders(text)) expect(lookup(payload, key), key).toBeDefined();
      }
    },
  );

  it("every NIT check row resolves in the oracle", () => {
    for (const check of NIT_CHECKS) {
      for (const key of check.keys) expect(lookup(payload, key), key).toBeDefined();
    }
  });

  it("guide copy contains no hand-typed rupee or kg figures", () => {
    for (const step of STEPS) {
      for (const text of [...step.actions, step.why, step.title]) {
        expect(text, text).not.toMatch(/₹\d|\d+(\.\d+)?\s?(kg|L)\b/);
      }
    }
  });
});

describe("formatValue keeps exact decimals", () => {
  it("formats money, signed percentages and Indian digit grouping", () => {
    expect(formatValue("7875.00", "INR")).toBe("₹7,875.00");
    expect(formatValue("-6.00", "±%")).toBe("−6.00%");
    expect(formatValue("5.00", "±%")).toBe("+5.00%");
    expect(formatValue("3", "%")).toBe("3%");
    expect(formatValue("123456.5", "INR")).toBe("₹1,23,456.5");
    expect(formatValue("43.125", "INR/kg")).toBe("₹43.125 / kg");
    expect(formatValue(false, "yesno")).toBe("No");
    expect(formatValue(undefined)).toBe("—");
  });

  it("fills placeholders from the oracle", () => {
    expect(fillTemplate("buy {inputs.steps.1_purchase.qty} kg", payload)).toBe("buy 60 kg");
  });
});

describe("guided tour and landing page", () => {
  beforeEach(() => {
    try {
      window.localStorage.clear(); // the Guide panel reopens at the last step viewed; start each test fresh
    } catch {
      /* storage unavailable in this runtime */
    }
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const body = url.endsWith("/expected")
          ? payload
          : { available: false, reason: "make benchmark has not been run on this server yet" };
        return new Response(JSON.stringify(body), { status: 200 });
      }),
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  const renderAt = (path: string) =>
    render(
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>,
    );

  it("walks all 11 steps with Next, showing oracle values", async () => {
    const user = userEvent.setup();
    renderAt("/guide");
    expect(screen.getByText("Step 1 of 11")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Next: Buy flour/ }));
    expect(screen.getByText("Step 2 of 11")).toBeInTheDocument();
    expect(await screen.findByText("₹43.125 / kg")).toBeInTheDocument();

    for (let i = 3; i <= 11; i++) {
      await user.click(screen.getByRole("button", { name: /^Next:/ }));
      expect(screen.getByText(`Step ${i} of 11`)).toBeInTheDocument();
    }
    expect(screen.getByRole("link", { name: /Finish/ })).toBeInTheDocument();
  });

  it("shows unbuilt screens honestly instead of linking to them", async () => {
    renderAt("/guide/purchase");
    expect(await screen.findByText("Coming in MP05")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Take me there/ })).not.toBeInTheDocument();
  });

  it("landing page shows NIT checks from the oracle and opens the Guide panel", async () => {
    const user = userEvent.setup();
    renderAt("/");
    const table = screen.getByRole("table");
    expect(
      await within(table).findByText("₹7,500.00 / ₹187.50 / ₹187.50 / ₹7,875.00"),
    ).toBeInTheDocument();
    expect(within(table).getByText("120 kg")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Guide/ }));
    const panel = screen.getByRole("dialog", { name: "Testing guide" });
    expect(within(panel).getByText("Step 1 of 11")).toBeInTheDocument();
    await user.click(within(panel).getByRole("button", { name: /Next/ }));
    expect(within(panel).getByText("Step 2 of 11")).toBeInTheDocument();
  });
});
