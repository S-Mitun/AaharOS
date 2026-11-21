import { afterEach, describe, expect, it, vi } from "vitest";
import { apiGet } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("session refresh (MP11 fix)", () => {
  it("refreshes once when several requests find the access cookie expired at the same time", async () => {
    let refreshed = false;
    const calls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        calls.push(url);
        if (url === "/api/auth/refresh") {
          await new Promise((r) => setTimeout(r, 10)); // still in flight when the other request asks
          refreshed = true;
          return new Response("{}", { status: 200 });
        }
        return refreshed
          ? new Response(JSON.stringify({ ok: url }), { status: 200 })
          : new Response(JSON.stringify({ error: { code: "unauthenticated" } }), { status: 401 });
      }),
    );
    const [a, b, c] = await Promise.all([
      apiGet<{ ok: string }>("/api/reports"),
      apiGet<{ ok: string }>("/api/collections"),
      apiGet<{ ok: string }>("/api/invoices"),
    ]);
    expect([a.ok, b.ok, c.ok]).toEqual(["/api/reports", "/api/collections", "/api/invoices"]);
    expect(calls.filter((u) => u === "/api/auth/refresh")).toHaveLength(1); // a second would revoke the session
  });
});
