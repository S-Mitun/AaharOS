import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { toTamil } from "./domTranslate";
import { translate } from "./i18n";

beforeEach(() => window.localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("Tamil / English", () => {
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

describe("Tamil across the whole page", () => {
  const signedOut = () =>
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ error: { code: "unauthenticated" } }), { status: 401 }),
      ),
    );

  it("translates body text and sentences with numbers, and puts the English back", async () => {
    signedOut();
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );
    await userEvent.click(await screen.findByRole("button", { name: "தமிழ்" }));
    await waitFor(() => expect(screen.getByText("யார் பயன்படுத்துகிறார்கள்")).toBeInTheDocument());
    expect(screen.getByText("தொழிற்சாலை நிர்வாகி திரையைத் திற →")).toBeInTheDocument();
    expect(screen.queryByText("Who uses it")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "English" }));
    await waitFor(() => expect(screen.getByText("Who uses it")).toBeInTheDocument());
  });

  it("matches patterns for sentences that carry numbers", () => {
    expect(toTamil("Explain this number: Run cost")).toBe("இந்த எண்ணை விளக்கு: தொகுப்புச் செலவு");
    expect(toTamil(" 88 packets ")).toBe(" 88 பாக்கெட்டுகள் ");
    expect(toTamil("DEMO Retailer A")).toBeNull(); // names stay as they are
  });
});
