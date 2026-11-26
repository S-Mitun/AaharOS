import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { markTourCompleted, rememberStep, stepsLeft, tourCompleted } from "./memory";
import { STEPS } from "./steps";

function serveSignedOut() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
      if (url === "/api/guide/expected")
        return json({ inputs: {}, nit_expected: {}, aaharos_expected: {} });
      return json({ error: { code: "unauthenticated", message: "please log in" } }, 401);
    }),
  );
}
const open = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );

beforeEach(() => window.localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("the guided tour comes first (deployment)", () => {
  it("keeps sign-up closed until the tour is finished", async () => {
    serveSignedOut();
    open("/sign-up");
    expect(
      await screen.findByRole("heading", { name: "Take the guided tour first" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Start the guided tour →" })).toHaveAttribute(
      "href",
      `/guide/${STEPS[0]!.id}`,
    );
  });

  it("refuses an own-account sign-in before the tour, but not a DEMO login", async () => {
    serveSignedOut();
    open("/sign-in");
    await userEvent.type(await screen.findByLabelText("Email"), "me@lakshmi-snacks.example");
    await userEvent.type(screen.getByLabelText("Password"), "my-own-pass-1");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("opens after the guided tour");
  });

  it("finishes only when every step was opened, then offers an own account", async () => {
    serveSignedOut();
    const last = STEPS[STEPS.length - 1]!;
    open(`/guide/${last.id}`);
    await userEvent.click(await screen.findByRole("button", { name: "Finish the tour" }));
    expect(await screen.findByText(/Open every step once/)).toBeInTheDocument();
    expect(tourCompleted()).toBe(false);
    for (const s of STEPS) rememberStep(s.id);
    await userEvent.click(screen.getByRole("button", { name: "Finish the tour" }));
    expect(
      await screen.findByRole("heading", { name: "You have finished the guided tour" }),
    ).toBeInTheDocument();
    expect(tourCompleted()).toBe(true);
    expect(screen.getByRole("link", { name: "Create your own factory" })).toHaveAttribute(
      "href",
      "/sign-up",
    );
  });

  it("restarts from step 1 at any time from the top bar, and stays open once finished", async () => {
    serveSignedOut();
    markTourCompleted();
    for (const s of STEPS) rememberStep(s.id);
    open("/sign-up");
    expect(
      await screen.findByRole("heading", { name: "Create your own factory" }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Restart tour/ }));
    expect(await screen.findByText(`Step 1 of ${STEPS.length}`)).toBeInTheDocument();
    expect(stepsLeft()).toHaveLength(STEPS.length - 1); // only step 1 seen in the new round
    expect(tourCompleted()).toBe(true);
  });
});
