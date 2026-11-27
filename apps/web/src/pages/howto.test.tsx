import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";

const played: string[] = [];
class FakeAudio {
  constructor(public src: string) {}
  onended: (() => void) | null = null;
  play() {
    played.push(this.src);
    return Promise.resolve();
  }
  pause() {}
}

beforeEach(() => {
  window.localStorage.clear();
  played.length = 0;
  vi.stubGlobal("Audio", FakeAudio);
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ error: { code: "x" } }), { status: 401 })),
  );
});
afterEach(() => vi.unstubAllGlobals());

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );

describe("the Instructions page", () => {
  it("is a main menu item and shows both step-by-step routines and where the voice is", async () => {
    renderAt("/");
    await userEvent.click(screen.getByRole("link", { name: "Instructions (step by step)" }));
    expect(
      await screen.findByRole("heading", { name: "Instructions", level: 1 }),
    ).toBeInTheDocument();
    const tour = screen.getByRole("article", { name: "Guided tour, step by step" });
    expect(within(tour).getAllByRole("listitem")).toHaveLength(8);
    const factory = screen.getByRole("article", { name: "Your own factory, step by step" });
    expect(within(factory).getAllByRole("listitem")).toHaveLength(8);
    expect(screen.getByRole("heading", { name: "Where is the voice guide?" })).toBeInTheDocument();
  });

  it("reads each routine aloud, and carries on in Tamil when Tamil is chosen", async () => {
    renderAt("/how-to");
    const factory = await screen.findByRole("article", { name: "Your own factory, step by step" });
    await userEvent.click(within(factory).getByRole("button", { name: /Listen/ }));
    expect(played).toEqual(["/voice/en/howto-factory.mp3"]);
    await userEvent.click(screen.getByRole("button", { name: "தமிழ்" }));
    await waitFor(() => expect(played.at(-1)).toBe("/voice/ta/howto-factory.mp3"));
    expect(screen.getByRole("heading", { name: "வழிமுறைகள்", level: 1 })).toBeInTheDocument();
  });
});
