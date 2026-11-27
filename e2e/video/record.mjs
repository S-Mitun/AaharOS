// Records the ~5-minute demo walkthrough (the guided tour, then a new factory's working day) against the local stack.
// Each screen stays up while its narration clip plays: durations.json (from media.py voice) sets the pace, and
// timeline.json records when each clip starts, for media.py mux.
// Run: docker compose --profile e2e run --rm -T e2e node video/record.mjs  -> e2e/video/out/*.webm
import { chromium } from "@playwright/test";
import { randomBytes } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";

const BASE = process.env.BASE_URL ?? "http://frontend:5180";
const DUR = JSON.parse(readFileSync("video/durations.json", "utf8"));
const pause = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1280, height: 720 },
  recordVideo: { dir: "video/out", size: { width: 1280, height: 720 } },
});
const page = await context.newPage();
const t0 = Date.now();
const timeline = [];
/** Start narration clip `id` now and keep the screen up until it has been spoken (plus a short breath). */
const say = async (id, extraMs = 0) => {
  timeline.push([id, Date.now() - t0]);
  await pause(DUR[id] * 1000 + 500 + extraMs);
};

const js = (fn, arg) => page.evaluate(fn, arg);
const go = async (path, wait = 1500) => {
  await js((p) => {
    history.pushState({}, "", p);
    dispatchEvent(new PopStateEvent("popstate"));
  }, path);
  await pause(wait);
};
const top = () => js(() => window.scrollTo({ top: 0, behavior: "smooth" }));
const scrollTo = (sel) =>
  js((s) => document.querySelector(s)?.scrollIntoView({ behavior: "smooth", block: "center" }), sel);
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
  js(
    (t) => [...document.querySelectorAll("main button, main a")].find((b) => b.textContent.trim().startsWith(t))?.click(),
    text,
  );

// ---------- home and instructions ----------
await page.goto(BASE + "/");
await js(() => {
  localStorage.clear();
  localStorage.setItem("aaharos.voice.auto", "0"); // the video carries its own narration
});
await page.goto(BASE + "/");
await pause(800);
await say("intro");
await go("/how-to", 800);
await scrollTo("#tour");
await say("howto");

// ---------- the guided tour ----------
const TOUR = ["tour-start", "t-purchase", "t-issue", "t-output", "t-order-a", "t-invoice", "t-order-b", "t-payment",
  "t-costs", "t-brief", "t-reports", "t-finish"];
await go("/guide/start", 800);
for (let i = 0; i < TOUR.length; i++) {
  await top();
  await say(TOUR[i], -1200);
  if (i === 1) {
    await page.locator("button.lang-switch").click(); // the Tamil switch, then back
    await say("tamil");
    await page.locator("button.lang-switch").click();
    await pause(600);
  }
  await scrollTo(".step-done");
  await pause(700);
  await page.locator(".step-done input").check();
  await pause(500);
  await page.locator(".guide-nav .btn-primary").click();
  await pause(700);
}
await scrollTo(".tour-finish");
await say("finish");

// ---------- create a new factory ----------
await page.getByRole("link", { name: "Create your own factory" }).first().click();
await pause(1200);
await page.getByLabel("Factory name").fill("DEMO Video Snacks");
await page.getByLabel("Your name").fill("Video Owner");
await page.getByLabel("Email").fill(`video-${Date.now()}@aaharos-demo.invalid`);
await page.getByLabel(/^Password/).fill(randomBytes(9).toString("base64url")); // throwaway local test account
await say("signup", -2500);
await page.getByRole("button", { name: "Create my factory" }).click();
await page.getByRole("heading", { name: "Your own factory, step by step" }).waitFor({ timeout: 30000 });
await pause(1500);

// ---------- the factory's working day ----------
await go("/admin/purchases/new");
await js(() => {
  const sel = document.querySelectorAll("main select")[1];
  const opt = [...sel.options].find((o) => o.text.startsWith("flour"));
  Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value").set.call(sel, opt.value);
  sel.dispatchEvent(new Event("change", { bubbles: true }));
});
await pause(500);
await set("Quantity", "60");
await set("Rate", "45");
await set("Supplier lot", "FL-VID-01");
await click("Post receipt");
await pause(1200);
await top();
await say("f-purchase");

await go("/production/batch/new");
await click("Start batch");
await pause(2000);
await set("cooking oil", "10.5");
await set("flour", "40");
await set("spice", "1.2");
await scrollTo("main table");
await say("f-batch");
await click("Issue materials");
await pause(2000);
await set("Good packets", "188");
await set("Damaged", "6");
await set("Cartons", "9");
await click("Seal failure");
await pause(500);
await click("Post batch");
await pause(1200);
await top();
await say("f-output");

const order = async (name, qty, clip) => {
  await go("/sales");
  await js((n) => {
    const card = [...document.querySelectorAll("main li, main article, main section > div")].find(
      (c) => c.textContent.includes(n) && c.querySelector("button, a"),
    );
    [...card.querySelectorAll("a,button")].find((b) => b.textContent.trim() === "New order").click();
  }, name);
  await pause(1800);
  await js((q) => {
    const el = document.querySelector("main input");
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(el, q);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }, String(qty));
  await say(clip, -1500);
  await click("Save order");
  await pause(2000);
};
await order("DEMO Retailer A", 150, "f-order-a");
await order("DEMO Distributor B", 120, "f-order-b");

await go("/admin/orders", 2500);
await click("DEMO Retailer A");
await pause(2500);
await click("Approve all");
await pause(1500);
await say("f-approve", -800);
await go("/admin/orders", 1800);
await click("DEMO Distributor B");
await pause(2000);
await scrollTo("main table");
await say("f-short");

await go("/admin/invoices", 2200);
await click("Create invoice");
await pause(3000);
await say("f-invoice");
await click("Preview the dispatch");
await pause(2000);
await js(() =>
  [...document.querySelectorAll("main h2, main h3")]
    .find((h) => /Stock movement/.test(h.textContent))
    ?.scrollIntoView({ behavior: "smooth", block: "center" }),
);
await say("f-dispatch", -1000);
await click("Record dispatch");
await pause(1500);

await go("/admin/collections", 2200);
await js(() => [...document.querySelectorAll("main button")].find((b) => b.textContent.includes("Retailer A"))?.click());
await pause(1500);
await set("Amount", "4000");
await click("Record payment");
await pause(1500);
await say("f-payment", -1000);

await go("/production/batch", 2200);
await set("Labour", "1200");
await set("Gas", "600");
await click("Add costs");
await pause(2500);
await say("f-costs");

await go("/owner", 2500);
await page.locator("button.lang-switch").click();
await pause(800);
await say("f-brief", 1500);
await page.locator("button.lang-switch").click();
await go("/leaks", 1500);
await js(() => document.querySelector('main a[href^="/leaks/"]')?.click());
await pause(2000);
await say("f-leaks");
await go("/auditor/reports?tab=gst", 3500);
await say("f-gst");
await go("/check", 3000);
await say("f-check", 1000);

writeFileSync("video/timeline.json", JSON.stringify(timeline));
await context.close(); // writes the video file
await browser.close();
console.log(`video recorded, ${Math.round((Date.now() - t0) / 1000)} s, ${timeline.length} narration clips`);
