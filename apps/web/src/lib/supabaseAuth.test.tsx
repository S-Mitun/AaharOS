import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";

const SUPA = "https://demo-ref.supabase.co";
const OWNER = {
  user: { id: "u1", email: "owner@aaharos.demo", display_name: "Owner (DEMO)" },
  organization: {
    id: "o1",
    code: "DEMO-FACTORY",
    name: "AaharOS Demo Snacks (DEMO)",
    kind: "LIVE",
  },
  role: "OWNER",
  permissions: ["report.read"],
};

function serveSupabaseMode() {
  const calls: { url: string; body: unknown }[] = [];
  let signedIn = false;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
      if (init?.method === "POST") calls.push({ url, body: JSON.parse(String(init.body ?? "{}")) });
      if (url === "/api/auth/config")
        return json({ mode: "supabase", supabase_url: SUPA, supabase_key: "sb_publishable_demo" });
      if (url === `${SUPA}/auth/v1/token?grant_type=password`)
        return json({ access_token: "supabase-token" });
      if (url === "/api/auth/exchange") {
        signedIn = true;
        return json(OWNER);
      }
      if (url === "/api/auth/me")
        return signedIn ? json(OWNER) : json({ error: { code: "not_authenticated" } }, 401);
      if (url === "/api/auth/refresh") return json({ error: { code: "no" } }, 401);
      return json({}, 200);
    }),
  );
  return calls;
}
afterEach(() => vi.unstubAllGlobals());

describe("hosted sign-in with Supabase Auth", () => {
  it("checks the password at Supabase, then opens the app's session with the token", async () => {
    const calls = serveSupabaseMode();
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/sign-in"]}>
        <App />
      </MemoryRouter>,
    );
    await user.type(await screen.findByLabelText("Email"), "owner@aaharos.demo");
    await user.type(screen.getByLabelText("Password"), "change-me-demo");
    await user.click(screen.getByRole("button", { name: /^Sign in$/ }));
    await waitFor(() => expect(calls.some((c) => c.url === "/api/auth/exchange")).toBe(true));
    expect(calls.find((c) => c.url.startsWith(SUPA))?.body).toEqual({
      email: "owner@aaharos.demo",
      password: "change-me-demo",
    });
    expect(calls.find((c) => c.url === "/api/auth/exchange")?.body).toEqual({
      access_token: "supabase-token",
    });
    expect(calls.some((c) => c.url === "/api/auth/login")).toBe(false);
  });
});
