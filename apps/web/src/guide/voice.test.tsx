import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";

const played: string[] = [];
class FakeAudio {
  src: string;
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(src: string) {
    this.src = src;
  }
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

describe("the voice guide", () => {
  it("reads the step in English, and switches to the Tamil voice the moment Tamil is chosen", async () => {
    render(
      <MemoryRouter initialEntries={["/guide/purchase"]}>
        <App />
      </MemoryRouter>,
    );
    await userEvent.click(await screen.findByRole("button", { name: "Listen to this step" }));
    expect(played).toEqual(["/voice/en/purchase.mp3"]);
    await userEvent.click(screen.getByRole("button", { name: "தமிழ்" }));
    await waitFor(() =>
      expect(played).toEqual(["/voice/en/purchase.mp3", "/voice/ta/purchase.mp3"]),
    );
    expect(screen.getByRole("heading", { name: "மாவு வாங்குதல்" })).toBeInTheDocument();
  });
});
