import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { translate } from "./i18n";

beforeEach(() => window.localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("Tamil / English (MP15)", () => {
  it("falls back to English for a string with no Tamil yet, never blank", () => {
    expect(translate("ta", "Guided tour")).toBe("வழிகாட்டும் சுற்றுலா");
    expect(translate("ta", "A sentence nobody translated")).toBe("A sentence nobody translated");
    expect(translate("en", "Guided tour")).toBe("Guided tour");
  });

  it("switches the shell to Tamil from the top bar and remembers it", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ error: { code: "unauthenticated" } }), { status: 401 }),
      ),
    );
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );
    await userEvent.click(await screen.findByRole("button", { name: "தமிழ்" }));
    expect(screen.getAllByText("வழிகாட்டும் சுற்றுலா").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "English" })).toBeInTheDocument();
    expect(window.localStorage.getItem("aaharos.lang")).toBe("ta");
    expect(document.documentElement.lang).toBe("ta");
  });
});
