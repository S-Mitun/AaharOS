import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";

const ADMIN = {
  user: { id: "u1", email: "admin@aaharos-demo.invalid", display_name: "Factory Admin (DEMO)" },
  organization: { id: "o1", code: "DEMO-FACTORY", name: "DEMO", kind: "LIVE" },
  role: "ADMIN",
  permissions: ["benchmark.run", "report.read"],
};
const BOARD = {
  available: true,
  generated_at: "2026-11-26T14:50:08+00:00",
  green: 26,
  total: 26,
  oracle_integrity: { passed: 10, failed: 0 },
  rows: [
    {
      n: 1,
      title: "Flour closing",
      owner_mp: "MP04",
      status: "GREEN",
      detail: "",
      expected: { k: "120" },
    },
    {
      n: 17,
      title: "Run cost",
      owner_mp: "MP07",
      status: "GREEN",
      detail: "",
      expected: { k: "5855.00" },
    },
  ],
};

function serve(who: unknown) {
  const posts: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
      if (url === "/api/auth/me")
        return who ? json(who) : json({ error: { code: "unauthenticated" } }, 401);
      if (init?.method === "POST") {
        posts.push(url);
        return json({ started: true }, 202);
      }
      if (url === "/api/guide/scoreboard") return json(BOARD);
      if (url === "/api/judge/status")
        return json({ judge_mode: true, running: false, seconds: null });
      return json({ error: { code: "not_found", message: "no" } }, 404);
    }),
  );
  return posts;
}
afterEach(() => vi.unstubAllGlobals());
const open = () =>
  render(
    <MemoryRouter initialEntries={["/judge"]}>
      <App />
    </MemoryRouter>,
  );

describe("the sample-day check", () => {
  it("shows the scoreboard to anyone, with each row linked to its tour step", async () => {
    serve(null);
    open();
    expect(await screen.findByText("26 of 26 correct")).toBeInTheDocument();
    expect(screen.getByText("Flour closing")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Sign in as the DEMO Factory admin/ }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Run the check now" })).not.toBeInTheDocument();
  });

  it("lets the DEMO admin run the replay again", async () => {
    const posts = serve(ADMIN);
    open();
    await userEvent.click(await screen.findByRole("button", { name: "Run the check now" }));
    await waitFor(() => expect(posts).toEqual(["/api/judge/run"]));
  });
});
