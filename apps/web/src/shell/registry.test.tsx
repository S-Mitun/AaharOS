import { render, screen } from "@testing-library/react";
import { matchRoutes, MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { homeFor, SCREENS } from "../guide/screens";
import { STEPS } from "../guide/steps";
import { GROUPS } from "../guide/types";
import type { Me } from "../lib/sessionContext";
import { appRoutes } from "../routes";
import { groupsFor, visibleScreens } from "./nav";

const me = (role: string, permissions: string[]): Me => ({
  user: { id: "u1", email: "x@aaharos-demo.invalid", display_name: `${role} (DEMO)` },
  organization: { id: "o1", code: "DEMO-FACTORY", name: "DEMO", kind: "LIVE" },
  role,
  permissions,
});
const SALESMAN = me("SALESMAN", ["customer.read", "order.read", "order.create", "stock.read"]);
const AUDITOR = me("AUDITOR", [
  "customer.read",
  "order.read",
  "stock.read",
  "report.read",
  "audit.read",
]);

function serveSignedOut() {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(JSON.stringify({ error: { code: "unauthenticated" } }), { status: 401 }),
    ),
  );
}
afterEach(() => vi.unstubAllGlobals());

describe("one registry for the sidebar, the routes and the tour (G9)", () => {
  it("gives every screen a route that is not the not-found page", () => {
    for (const s of Object.values(SCREENS)) {
      const matched = matchRoutes(appRoutes, s.route);
      const leaf = matched?.[matched.length - 1]?.route;
      expect(leaf?.path, s.route).not.toBe("*");
    }
  });

  it("lists every screen in its group in the sidebar for a visitor", () => {
    const listed = groupsFor(null).flatMap((g) => g.screens);
    expect(listed.map((s) => s.route).sort()).toEqual(
      Object.values(SCREENS)
        .filter((s) => !s.hidden)
        .map((s) => s.route)
        .sort(),
    );
    expect(groupsFor(null).map((g) => g.group)).toEqual([...GROUPS]);
  });

  it("points every tour step at a registered screen", () => {
    for (const step of STEPS) expect(SCREENS[step.screen], step.id).toBeDefined();
  });

  it("hides what a role cannot use", () => {
    const salesman = visibleScreens(SALESMAN).map((s) => s.group);
    expect(salesman).toContain("Salesman");
    expect(salesman).not.toContain("Admin");
    expect(
      visibleScreens(AUDITOR).some(
        (s) => s.group === "Salesman" && s.permission === "order.create",
      ),
    ).toBe(false);
  });

  it("lands a salesman on Today and other roles on today's pages (G7)", () => {
    expect(homeFor("SALESMAN")).toBe("/sales");
    expect(homeFor("OWNER")).toBe("/leaks");
  });
});

describe("the shell", () => {
  const renderAt = (path: string) =>
    render(
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>,
    );

  it("opens on the guided-tour landing page with the sidebar", async () => {
    serveSignedOut();
    renderAt("/");
    expect(await screen.findByRole("navigation", { name: "All screens" })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Guided tour/ }).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /Menu/ })).toBeInTheDocument();
  });

  it("shows an honest Coming page for a screen not built yet, with no numbers", async () => {
    serveSignedOut();
    renderAt("/admin/orders");
    expect(await screen.findByRole("heading", { name: /Order inbox/ })).toBeInTheDocument();
    expect(screen.getByText(/Coming in MP09/)).toBeInTheDocument();
    expect(document.querySelector("main")?.textContent).not.toMatch(/₹/);
  });

  it("asks a visitor to sign in on a screen that needs data", async () => {
    serveSignedOut();
    renderAt("/sales");
    expect(
      await screen.findByRole("heading", { name: /Sign in to see the salesman app/ }),
    ).toBeInTheDocument();
  });
});
