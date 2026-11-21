import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * MP08 gate (G8), on a fresh SIM scratch tenant made by `python -m app.cli.seed_e2e` (never the DEMO factory):
 * 1. an online order is received by the factory
 * 2. an offline order is saved on the phone and, after reconnecting, reaches the server exactly once
 * 3. a duplicate send (the reply lost on the way back) is replayed, not doubled
 * 4. the time to submit a repeat order, measured and printed (no target is claimed)
 * 5. a stale price is flagged (a new price list version published while the phone is offline)
 */

interface Tenant {
  organization_code: string;
  emails: Record<"SALESMAN" | "ADMIN" | "OWNER", string>;
  password: string;
  item_id: string;
  customer_id: string;
}
const tenant = JSON.parse(readFileSync(resolve(__dirname, "../.tenant.json"), "utf8")) as Tenant;

test.describe.configure({ mode: "serial" });

async function signIn(page: Page, email: string) {
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(tenant.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
}

async function apiAs(request: APIRequestContext, email: string) {
  const r = await request.post("/api/auth/login", { data: { email, password: tenant.password } });
  expect(r.ok()).toBeTruthy();
}

async function serverOrderCount(request: APIRequestContext): Promise<number> {
  const r = await request.get("/api/orders");
  expect(r.ok()).toBeTruthy();
  return ((await r.json()) as { orders: unknown[] }).orders.length;
}

async function newOrder(page: Page, packets: string) {
  await page.goto("/sales");
  await page.getByRole("main").getByRole("link", { name: "New order" }).click();
  const box = page.getByRole("textbox", { name: /packets/ });
  await box.fill(packets);
  await page.getByRole("button", { name: "Save order" }).click();
}

test("1. an online order is received by the factory", async ({ page }) => {
  await signIn(page, tenant.emails.SALESMAN);
  await expect(page).toHaveURL(/\/sales$/);
  await expect(page.getByText("DEMO Retailer A")).toBeVisible();
  await newOrder(page, "150");
  await expect(page.getByText("Received by factory").first()).toBeVisible();
  await expect(page.locator(".order-no")).toHaveText(/^SO\/\d{2}-\d{2}\/\d{6}$/);
  await expect(page.getByText("₹7,500.00")).toBeVisible();
});

test("2. an offline order reaches the server exactly once after reconnecting", async ({
  page,
  context,
  request,
}) => {
  await apiAs(request, tenant.emails.SALESMAN);
  const before = await serverOrderCount(request);
  await signIn(page, tenant.emails.SALESMAN);
  await expect(page.getByText("DEMO Retailer A")).toBeVisible();
  // load the order screen once online so the phone has the price list, then lose the network
  await page.getByRole("main").getByRole("link", { name: "New order" }).click();
  await expect(page.getByRole("textbox", { name: /packets/ })).toBeVisible();
  await context.setOffline(true);
  await page.getByRole("textbox", { name: /packets/ }).fill("40");
  await page.getByRole("button", { name: "Save order" }).click();
  await expect(page.locator(".chip", { hasText: "Saved on phone" })).toBeVisible();
  await expect(page.getByText("Received by factory")).toHaveCount(0);
  expect(await serverOrderCount(request)).toBe(before);

  await context.setOffline(false);
  await expect(page.locator(".chip", { hasText: "Received by factory" })).toBeVisible();
  await expect(page.locator(".order-no")).toHaveText(/^SO\//);
  expect(await serverOrderCount(request)).toBe(before + 1);
});

test("3. a duplicate send is replayed, never doubled", async ({ page, request }) => {
  await apiAs(request, tenant.emails.SALESMAN);
  const before = await serverOrderCount(request);
  await signIn(page, tenant.emails.SALESMAN);
  await expect(page.getByText("DEMO Retailer A")).toBeVisible();
  // the first POST reaches the factory, but its reply is lost on the way back to the phone
  let dropped = 0;
  const keys: string[] = [];
  await page.route("**/api/orders", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    keys.push(route.request().headers()["idempotency-key"] ?? "");
    const response = await route.fetch();
    if (dropped === 0) {
      dropped += 1;
      expect(response.status()).toBe(201);
      return route.abort("connectionreset");
    }
    expect(response.status()).toBe(200); // the factory recognised the key: replayed
    return route.fulfill({ response });
  });
  await newOrder(page, "12");
  // the phone never saw the reply, so it keeps the order and retries by itself (backoff: about 2 s)
  await expect(page.locator(".chip", { hasText: "Received by factory" })).toBeVisible();
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
  expect(await serverOrderCount(request)).toBe(before + 1);
});

test("4. time to submit a repeat order (measured, printed)", async ({ page }) => {
  await signIn(page, tenant.emails.SALESMAN);
  await expect(page.getByText("DEMO Retailer A")).toBeVisible();
  const started = Date.now();
  await page.getByRole("link", { name: "Repeat last order" }).click();
  await expect(page.getByRole("textbox", { name: /packets/ })).not.toHaveValue("0");
  await page.getByRole("button", { name: "Save order" }).click();
  await expect(page.locator(".chip", { hasText: "Received by factory" })).toBeVisible();
  const ms = Date.now() - started;
  console.log(`\nREPEAT-ORDER TIME TO SUBMIT: ${ms} ms (tap "Repeat last order" -> "Received by factory", automated, dev stack)\n`);
  test.info().annotations.push({ type: "repeat-order-ms", description: String(ms) });
});

test("5. a stale price is flagged when prices change while the phone is offline", async ({
  page,
  context,
  playwright,
}) => {
  await signIn(page, tenant.emails.SALESMAN);
  await expect(page.getByText("DEMO Retailer A")).toBeVisible();
  await page.getByRole("main").getByRole("link", { name: "New order" }).click();
  await expect(page.getByText("₹50.00").first()).toBeVisible();
  await context.setOffline(true);
  await page.getByRole("textbox", { name: /packets/ }).fill("30");
  await page.getByRole("button", { name: "Save order" }).click();
  await expect(page.locator(".chip", { hasText: "Saved on phone" })).toBeVisible();

  // meanwhile the factory admin publishes price list v2
  const admin = await playwright.request.newContext({ baseURL: process.env.BASE_URL ?? "http://localhost:5180" });
  await apiAs(admin, tenant.emails.ADMIN);
  const published = await admin.post("/api/price-lists", {
    data: {
      code: "GENERAL",
      effective_from: "2026-04-01",
      items: [{ item_id: tenant.item_id, price_ex_tax: "52.00" }],
    },
  });
  expect(published.status()).toBe(201);
  expect(((await published.json()) as { version: number }).version).toBe(2);
  await admin.dispose();

  await context.setOffline(false);
  await expect(page.locator(".chip", { hasText: "Received by factory" })).toBeVisible();
  await expect(page.getByText("Price changed: admin will confirm")).toBeVisible();
  await expect(page.getByText(/was in force when the factory received it/)).toBeVisible();
});
