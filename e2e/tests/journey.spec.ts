import { expect, test } from "@playwright/test";

/**
 * The visitor's journey on the one address (deployment review): the guided tour is the first task; sign-up stays
 * closed until every step was opened; the tour then offers an own account; the new factory opens the MP11-MP14
 * screens; "Restart tour" in the top bar starts again from step 1, any number of times.
 */
test("a new visitor takes the tour, then works in their own factory", async ({ page }) => {
  test.setTimeout(180_000); // twelve tour steps, a sign-up and five screens, while other specs run in parallel
  await page.goto("/sign-up");
  await expect(page.getByRole("heading", { name: "Take the guided tour first" })).toBeVisible();
  await page.getByRole("link", { name: /Start the guided tour/ }).click();

  await expect(page.getByText(/^Step 1 of \d+$/)).toBeVisible();
  const total = Number((await page.getByText(/^Step 1 of \d+$/).textContent())?.split(" of ")[1]);
  for (let step = 2; step <= total; step++) {
    // the keyboard path (focus + Enter), as a keyboard user walks the tour; the page re-lays out after each step
    await page.getByLabel("I have done this step").check();
    await page.getByRole("button", { name: /^Next:/ }).press("Enter");
    await expect(page.getByText(`Step ${step} of ${total}`)).toBeVisible();
  }
  await page.getByLabel("I have done this step").check();
  await page.getByRole("button", { name: "Finish the tour" }).press("Enter");
  await expect(page.getByRole("heading", { name: "You have finished the guided tour" })).toBeVisible();
  await page.getByRole("link", { name: "Create your own factory" }).click();

  const email = `journey-${Date.now()}@example.com`;
  await page.getByLabel("Factory name").fill("DEMO Journey Snacks");
  await page.getByLabel("Your name").fill("DEMO Journey Owner");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel(/^Password/).fill("journey-pass-1");
  await page.getByRole("button", { name: "Create my factory" }).click();
  // a new factory opens on its step-by-step instructions first, then the Morning brief is one click away
  await expect(page.getByRole("heading", { name: "Your own factory, step by step" })).toBeVisible({
    timeout: 30_000,
  });
  await page.getByRole("link", { name: "Open my Morning brief →" }).click();
  await expect(page.getByRole("heading", { name: "Morning brief" })).toBeVisible();
  const me = (await (await page.request.get("/api/auth/me")).json()) as {
    role: string;
    organization: { name: string };
  };
  expect(me.role).toBe("OWNER");
  expect(me.organization.name).toBe("DEMO Journey Snacks");

  for (const [path, heading] of [
    ["/production/trace", "Trace and recall"],
    ["/production/food-safety", "Oil and fill weights"],
    ["/admin/trips", "Trips and cost-to-serve"],
    ["/sales/freshness", "Freshness"],
    ["/auditor/reports", "Reports"],
  ] as const) {
    await page.goto(path);
    await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
  }
  await page.goto("/production/trace");
  await page.getByRole("button", { name: /OPEN-LOT/ }).click();
  await expect(page.getByText("opening stock: no batch record behind this lot")).toBeVisible();

  await page.getByRole("button", { name: /Restart tour/ }).click();
  await expect(page.getByText(/^Step 1 of \d+$/)).toBeVisible();
  await page.goto("/sign-up"); // finishing once keeps own accounts open
  await expect(page.getByRole("heading", { name: "Create your own factory" })).toBeVisible();
});
