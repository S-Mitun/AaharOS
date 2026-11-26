import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { Num } from "../components/Num";
import { formatAmount } from "../lib/amount";
import { roundDecimal, sharePercent } from "../lib/decimal";
import { checkFor, type Costing } from "../lib/leaks";

// Recorded from a real benchmark replay: `python -m app.cli.record_fixture` (every number from the database).
const fixture = JSON.parse(
  readFileSync(resolve(__dirname, "../test-fixtures/b001.json"), "utf8"),
) as {
  costing: Costing;
  runs: { runs: unknown[] };
};
const ME = {
  user: { id: "u1", email: "auditor@aaharos-demo.invalid", display_name: "Auditor (DEMO)" },
  organization: {
    id: "o1",
    code: "DEMO-FACTORY",
    name: "AaharOS Demo Snacks (DEMO)",
    kind: "LIVE",
  },
  role: "AUDITOR",
  permissions: ["report.read"],
};

function serve(signedIn: boolean) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
      if (url === "/api/auth/me")
        return signedIn ? json(ME) : json({ error: { code: "unauthenticated" } }, 401);
      if (url === "/api/auth/refresh") return json({ error: { code: "unauthenticated" } }, 401);
      if (url === "/api/auth/login") return json(ME);
      if (url === "/api/runs") return json(fixture.runs);
      if (url.endsWith("/costing")) return json(fixture.costing);
      return json({ available: false });
    }),
  );
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );

describe("exact decimals, no floats", () => {
  it("rounds half up on the digits", () => {
    expect(roundDecimal("31.143617", 2)).toBe("31.14");
    expect(roundDecimal("-4.255", 2)).toBe("-4.26");
    expect(roundDecimal("5855", 2)).toBe("5855.00");
    expect(roundDecimal("-0.004", 2)).toBe("0.00");
    expect(roundDecimal("0.995", 2)).toBe("1.00");
  });

  it("formats rupees, rates and quantities", () => {
    expect(formatAmount("5855.00", "INR")).toBe("₹5,855.00");
    expect(formatAmount("31.143617", "INR/packet")).toBe("₹31.14 / packet");
    expect(formatAmount("-6.00", "INR")).toBe("−₹6.00");
    expect(formatAmount("10.5", "L")).toBe("10.5 L");
    expect(formatAmount("1", "batches")).toBe("1 batch");
    expect(formatAmount("1.53", "batches")).toBe("1.53 batches");
    expect(formatAmount("12", "packets")).toBe("12 packets");
    expect(sharePercent("-6.00", "307.20")).toBe(1);
  });
});

describe("Explain this number", () => {
  it("opens a popover with the formula and sourced inputs, and Escape closes it", async () => {
    const user = userEvent.setup();
    render(<Num value={fixture.costing.cost.per_good_unit!} label="Cost per good packet" />);
    expect(screen.getByText("₹31.14 / packet")).toBeInTheDocument();
    const button = screen.getByRole("button", {
      name: "Explain this number: Cost per good packet",
    });
    await user.click(button);
    const pop = screen.getByRole("dialog", { name: "How Cost per good packet is worked out" });
    expect(within(pop).getByText("run cost / good units")).toBeInTheDocument();
    expect(within(pop).getByText("₹5,855.00")).toBeInTheDocument();
    expect(within(pop).getAllByText(/Production run/).length).toBeGreaterThan(0);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(button).toHaveFocus();
  });
});

describe("Where profit leaks", () => {
  it("shows batch B-001's costing, the ranked waterfall and checks, all from the API", async () => {
    serve(true);
    renderAt(`/leaks/${fixture.costing.run_id}`);
    expect(await screen.findByRole("heading", { name: /Batch B-001/ })).toBeInTheDocument();
    expect(screen.getByText("✓ Cost final")).toBeInTheDocument();
    for (const text of ["₹5,855.00", "₹31.14 / packet", "₹5,423.80", "₹431.20"]) {
      expect(screen.getAllByText(text).length).toBeGreaterThan(0);
    }
    const rows = within(screen.getByRole("list", { name: /Variance waterfall/ })).getAllByRole(
      "listitem",
    );
    expect(rows[0]).toHaveTextContent("yield loss MURUKKU-200G");
    expect(rows[0]).toHaveTextContent("₹307.20");
    expect(rows.at(-1)).toHaveTextContent("−₹6.00");
    expect(rows.at(-1)).toHaveTextContent("▼ Saves");
    const shown = rows.map((r) => /−?₹[\d,.]+/.exec(r.textContent ?? "")?.[0]);
    const expected = fixture.costing
      .waterfall!.components.filter((c) => c.value !== "0.00")
      .map((c) => formatAmount(c.value, "INR"));
    expect(shown).toEqual(expected); // every figure on the page is the database's figure
    expect(
      screen.getByText(/Check sealing and handling of pouch 200g for batch B-001 \(6 damaged\)/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Possibilities to verify on the floor, not findings/),
    ).toBeInTheDocument();
    const fifo = screen.getByRole("row", { name: /FIFO/ });
    expect(fifo).toHaveTextContent("₹5,810.00");
    expect(fifo).toHaveTextContent("₹30.90 / packet");
  });

  it("lists completed batches", async () => {
    serve(true);
    renderAt("/leaks");
    expect(await screen.findByRole("link", { name: "Batch B-001" })).toBeInTheDocument();
  });

  it("sends a visitor who is not signed in to the sign-in page, then back", async () => {
    const calls = serve(false);
    const user = userEvent.setup();
    renderAt("/leaks");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Email"), "auditor@aaharos-demo.invalid");
    await user.type(screen.getByLabelText("Password"), "DEMO-only");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("link", { name: "Batch B-001" })).toBeInTheDocument();
    const login = calls.find((c) => c.url === "/api/auth/login");
    expect(JSON.parse(String(login?.init?.body))).toEqual({
      email: "auditor@aaharos-demo.invalid",
      password: "DEMO-only",
    });
  });
});

describe("check prompts are checks, never causes", () => {
  it("words every waterfall part as something to verify", () => {
    for (const c of fixture.costing.waterfall!.components) {
      const text = checkFor(c, "B-001");
      if (text) expect(text).toMatch(/^(Check|Confirm) /);
    }
  });
});
