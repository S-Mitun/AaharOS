import { defineConfig, devices } from "@playwright/test";

/** MP08 (G8): the salesman scenarios against the running dev stack, on a phone-sized Chromium. */
export default defineConfig({
  testDir: "./tests",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:5180",
    ...devices["Pixel 7"],
    trace: "retain-on-failure",
  },
});
