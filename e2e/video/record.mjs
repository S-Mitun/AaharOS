// Records a ~5-minute walkthrough video of AaharOS (the guided tour, then a new factory's working day) against the
// local stack. Run: docker compose --profile e2e run --rm -T e2e node video/record.mjs  -> e2e/video/out/*.webm
import { chromium } from "@playwright/test";
import { randomBytes } from "node:crypto";

const BASE = process.env.BASE_URL ?? "http://frontend:5180";
const pause = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1280, height: 720 },
  recordVideo: { dir: "video/out", size: { width: 1280, height: 720 } },
});
const page = await context.newPage();
const js = (fn, arg) => page.evaluate(fn, arg);
const go = async (path, wait = 2500) => {
  await js((p) => {
    history.pushState({}, "", p);
    dispatchEvent(new PopStateEvent("popstate"));
  }, path);
  await pause(wait);
};
const top = () => js(() => window.scrollTo({ top: 0, behavior: "smooth" }));
const scrollTo = (sel) =>
  js((s) => document.querySelector(s)?.scrollIntoView({ behavior: "smooth", block: "center" }), sel);

// ---------- home and instructions (about 25 s) ----------
await page.goto(BASE + "/");
await js(() => {
  localStorage.clear();
  localStorage.setItem("aaharos.voice.auto", "0"); // the video has no sound track
});
await page.goto(BASE + "/");
await pause(5000);
await go("/how-to", 6000);
await scrollTo("#tour");
await pause(5000);
await scrollTo("#own-factory");
await pause(5000);

// ---------- the guided tour, 12 steps (about 2 min 15 s) ----------
await go("/guide/start", 2500);
for (let i = 0; i < 12; i++) {
  await top();
  await pause(4500); // read the card
  await scrollTo(".step-done");
  await pause(1500);
  await page.locator(".step-done input").check();
  await pause(1500);
  if (i === 1) {
    // show the Tamil switch on step 2, then back to English
    await page.locator("button.lang-switch").click();
    await top();
    await pause(4500);
    await page.locator("button.lang-switch").click();
    await pause(1000);
    await scrollTo(".step-done");
  }
  const button = page.locator(".guide-nav .btn-primary");
  await button.click();
  await pause(1500);
}
await scrollTo(".tour-finish");
await pause(3500);

// ---------- create a new factory (about 25 s) ----------
await page.getByRole("link", { name: "Create your own factory" }).first().click();
await pause(2000);
await page.getByLabel("Factory name").fill("DEMO Video Snacks");
await page.getByLabel("Your name").fill("Video Owner");
await page.getByLabel("Email").fill(`video-${Date.now()}@aaharos-demo.invalid`);
await page.getByLabel(/^Password/).fill(randomBytes(9).toString("base64url")); // throwaway local test account
await pause(1500);
await page.getByRole("button", { name: "Create my factory" }).click();
await page.getByRole("heading", { name: "Your own factory, step by step" }).waitFor({ timeout: 30000 });
await pause(5000);

// ---------- the factory's working day (about 1 min 45 s) ----------
const set = (label, value) =>
  js(
    ([l, v]) => {
      const el = [...document.querySelectorAll("main input")].find((i) =>
        (i.labels?.[0]?.textContent || i.getAttribute("aria-label") || "").startsWith(l),
      );
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(el, v);
      el.dispatchEvent(new Event("input", { bubbles: true }));
    },
    [label, value],
  );
const click = (text) =>
  js((t) => [...document.querySelectorAll("main button, main a")].find((b) => b.textContent.trim().startsWith(t))?.click(), text);

// purchase
await go("/admin/purchases/new");
await js(() => {
  const sel = document.querySelectorAll("main select")[1];
  const opt = [...sel.options].find((o) => o.text.startsWith("flour"));
  Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value").set.call(sel, opt.value);
  sel.dispatchEvent(new Event("change", { bubbles: true }));
});
await pause(800);
await set("Quantity", "60");
await set("Rate", "45");
await set("Supplier lot", "FL-VID-01");
await pause(1500);
await click("Post receipt");
await pause(1500);
await top();
await pause(4000);

// batch: start, issue, output
await go("/production/batch/new");
await click("Start batch");
await pause(2500);
await set("cooking oil", "10.5");
await set("flour", "40");
await set("spice", "1.2");
await scrollTo("main table");
await pause(4000);
await click("Issue materials");
await pause(2500);
await set("Good packets", "188");
await set("Damaged", "6");
await set("Cartons", "9");
await click("Seal failure");
await pause(2000);
await click("Post batch");
await pause(1500);
await top();
await pause(4500);

// two orders on the salesman screen
const order = async (name, qty) => {
  await go("/sales");
  await js((n) => {
    const card = [...document.querySelectorAll("main li, main article, main section > div")].find(
      (c) => c.textContent.includes(n) && c.querySelector("button, a"),
    );
    [...card.querySelectorAll("a,button")].find((b) => b.textContent.trim() === "New order").click();
  }, name);
  await pause(2200);
  await js((q) => {
    const el = document.querySelector("main input");
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(el, q);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }, String(qty));
  await pause(2500);
  await click("Save order");
  await pause(3500);
};
await order("DEMO Retailer A", 150);
await order("DEMO Distributor B", 120);

// admin: approve A, show B's shortage
await go("/admin/orders", 3000);
await click("DEMO Retailer A");
await pause(3000);
await click("Approve all");
await pause(3000);
await go("/admin/orders", 2000);
await click("DEMO Distributor B");
await pause(2500);
await scrollTo("main table");
await pause(5000);

// invoice and dispatch
await go("/admin/invoices", 2500);
await click("Create invoice");
await pause(4000);
await click("Preview the dispatch");
await pause(2500);
await js(() => [...document.querySelectorAll("main h2, main h3")].find((h) => /Stock movement/.test(h.textContent))?.scrollIntoView({ behavior: "smooth", block: "center" }));
await pause(4000);
await click("Record dispatch");
await pause(2000);
await top();
await pause(3500);

// payment
await go("/admin/collections", 2500);
await js(() => [...document.querySelectorAll("main button")].find((b) => b.textContent.includes("Retailer A"))?.click());
await pause(2000);
await set("Amount", "4000");
await pause(1000);
await click("Record payment");
await pause(4500);

// run costs and margin
await go("/production/batch", 2500);
await set("Labour", "1200");
await set("Gas", "600");
await pause(1000);
await click("Add costs");
await pause(5500);

// owner's morning brief (in Tamil for a moment), where profit leaks, reports
await go("/owner", 5000);
await page.locator("button.lang-switch").click();
await pause(4500);
await page.locator("button.lang-switch").click();
await go("/leaks", 2000);
await js(() => document.querySelector('main a[href^="/leaks/"]')?.click());
await pause(5000);
await go("/auditor/reports?tab=gst", 6000);
await go("/check", 6000);

await context.close(); // writes the video file
await browser.close();
console.log("video recorded");
