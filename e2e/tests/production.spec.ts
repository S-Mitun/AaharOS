import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

/**
 * MP15: NIT steps 1, 2, 3 and 8 on the production screens, in the browser only, on the fresh SIM tenant made by
 * `python -m app.cli.seed_e2e` (NIT's opening stock). The run cost must come out at the oracle's Rs 31.14 a packet.
 */
interface Tenant {
  emails: Record<"PRODUCTION" | "OWNER", string>;
  password: string;
}
const tenant = JSON.parse(readFileSync(resolve(__dirname, "../.tenant.json"), "utf8")) as Tenant;

test("purchase, batch card and run costs give Rs 31.14 a packet", async ({ page }) => {
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill(tenant.emails.OWNER);
  await page.getByLabel("Password").fill(tenant.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Morning brief" })).toBeVisible();

  // step 1: buy 60 kg of flour at Rs 45, with the supplier's lot
  await page.goto("/admin/purchases/new");
  await page.getByRole("combobox", { name: /^Item/ }).selectOption({ label: "flour (kg)" });
  await page.getByLabel(/^Quantity/).fill("60");
  await page.getByLabel(/^Rate/).fill("45.00");
  await page.getByLabel("Supplier lot no.").fill("E2E-FL-1");
  await page.getByRole("button", { name: "Post receipt" }).click();
  await expect(page.getByText(/Receipt GRN\/\d{2}-\d{2}\/\d{6} posted/)).toBeVisible();
  await expect(page.getByText("₹43.13 / kg")).toBeVisible(); // 43.125, shown to paise

  // steps 2-3: the batch card
  await page.goto("/production/batch/new");
  await page.getByRole("button", { name: "Start batch" }).click();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: /^Batch B-\d{3}/ })).toBeVisible();
  await page.getByLabel("flour used, kg").fill("40");
  await page.getByLabel("cooking oil used, L").fill("10.5");
  await page.getByLabel("spice mix used, kg").fill("1.2");
  await expect(page.getByText("160 → 120 kg")).toBeVisible(); // the stock-impact preview: NIT row 1
  await page.getByRole("button", { name: "Issue materials" }).click();
  await expect(page.getByText(/Materials issued on MI\//)).toBeVisible();
  await page.getByLabel(/^Good packets/).fill("188");
  await page.getByLabel("Damaged pouches").fill("6");
  await page.getByLabel("Cartons used").fill("9");
  await page.getByRole("button", { name: "Seal failure" }).click();
  await page.getByRole("button", { name: "Post batch" }).click();
  await expect(page.getByText(/posted: finished packets are in stock/)).toBeVisible();
  await expect(page.getByText(/yield MURUKKU-200G -6.00%/)).toBeVisible();

  // step 8: labour and gas, then the cost per good packet
  await page.goto("/production/batch");
  await page.getByLabel("Labour ₹").fill("1200");
  await page.getByLabel("Gas / power ₹").fill("600");
  await page.getByRole("button", { name: "Add costs" }).click();
  await expect(page.getByText("₹5,855.00")).toBeVisible();
  await expect(page.getByText("₹31.14 / packet")).toBeVisible();
  await page.getByRole("button", { name: "Mark costs final" }).click();
  await expect(page.getByText("Costs are final for this batch.")).toBeVisible();
});
