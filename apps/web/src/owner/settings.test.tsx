import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";

const me = (role: string, permissions: string[]) => ({
  user: { id: "u1", email: "x@aaharos.demo", display_name: `${role} (DEMO)` },
  organization: {
    id: "o1",
    code: "DEMO-FACTORY",
    name: "AaharOS Demo Snacks (DEMO)",
    kind: "LIVE",
  },
  role,
  permissions,
});

function serve(who: unknown) {
  const writes: { method: string; url: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
      if (url === "/api/auth/me") return json(who);
      if (init?.method === "PUT" || init?.method === "POST") {
        writes.push({ method: init.method, url, body: JSON.parse(String(init.body ?? "{}")) });
        return json({}, init.method === "POST" ? 201 : 200);
      }
      if (url === "/api/settings")
        return json({
          on: "2026-11-27",
          settings: [
            {
              key: "freshness.alert_days",
              label: "Freshness alert after",
              unit: "days",
              value: "10",
            },
          ],
        });
      if (url === "/api/tax/rules")
        return json({
          rules: [
            {
              id: "t1",
              hsn: "2106",
              rate_pct: "5",
              effective_from: "2025-04-01",
              effective_to: null,
            },
          ],
        });
      return json({ error: { code: "not_found", message: "no" } }, 404);
    }),
  );
  return writes;
}
afterEach(() => vi.unstubAllGlobals());

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );

describe("Owner → Settings", () => {
  it("changes a setting from a date and lists the GST rates", async () => {
    const writes = serve(me("OWNER", ["report.read", "settings.manage"]));
    const user = userEvent.setup();
    renderAt("/owner/settings");
    expect(
      await screen.findByRole("row", { name: /Freshness alert after 10 days/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("row", { name: /2106 5% 2025-04-01 open/ })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Change Freshness alert after" }));
    const value = screen.getByLabelText("New value");
    await user.clear(value);
    await user.type(value, "12");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]).toMatchObject({ method: "PUT", url: "/api/settings/freshness.alert_days" });
    expect((writes[0]!.body as { value: string }).value).toBe("12");
    expect(await screen.findByText(/Saved: the new value applies from/)).toBeInTheDocument();
  });

  it("is read-only for the auditor", async () => {
    serve(me("AUDITOR", ["report.read"]));
    renderAt("/owner/settings");
    expect(await screen.findByRole("row", { name: /Freshness alert after/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Change/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add GST rate" })).not.toBeInTheDocument();
  });
});
