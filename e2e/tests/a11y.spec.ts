import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/**
 * MP15 accessibility: axe (WCAG 2.1 A and AA rules) finds no serious or critical violation on the main screens, signed
 * out (the tour, sign-in, the sample-day check) and signed in (the owner's screens on the SIM tenant from seed_e2e).
 */
interface Tenant {
  emails: Record<"OWNER", string>;
  password: string;
}
const tenant = JSON.parse(readFileSync(resolve(__dirname, "../.tenant.json"), "utf8")) as Tenant;

async function expectAccessible(page: Page, path: string, ready: RegExp) {
  await page.goto(path);
  await expect(page.getByRole("heading", { name: ready }).first()).toBeVisible();
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const bad = results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(", ")})`);
  expect(bad, `${path}`).toEqual([]);
}

test("signed-out screens have no serious accessibility violation", async ({ page }) => {
  await expectAccessible(page, "/", /Every gram traced/);
  await expectAccessible(page, "/guide", /Guided tour/);
  await expectAccessible(page, "/sign-in", /^Sign in$/);
  await expectAccessible(page, "/sign-up", /Take the guided tour first/);
  await expectAccessible(page, "/check", /Sample-day check/);
  await expectAccessible(page, "/guide/purchase", /Guided tour/); // with the voice guide
});

test("the owner's screens have no serious accessibility violation", async ({ page }) => {
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill(tenant.emails.OWNER);
  await page.getByLabel("Password").fill(tenant.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Morning brief" })).toBeVisible();
  for (const [path, heading] of [
    ["/owner", /Morning brief/],
    ["/admin/orders", /Order inbox/],
    ["/admin/purchases/new", /New purchase receipt/],
    ["/production/batch/new", /Batch card/],
    ["/production/batch", /Run costs/],
    ["/production/planner", /Batch planner/],
    ["/production/trace", /Trace and recall/],
    ["/production/food-safety", /Oil and fill weights/],
    ["/admin/trips", /Trips and cost-to-serve/],
    ["/auditor/reports", /Reports/],
    ["/owner/settings", /^Settings$/],
    ["/sales", /Today/],
  ] as const) {
    await expectAccessible(page, path, heading);
  }
});
