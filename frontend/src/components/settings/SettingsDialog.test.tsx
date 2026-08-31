import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { render, screen, cleanup, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "@/test/mocks/server";
import { useSettingsModalStore } from "@/store/settingsModalStore";
import { SettingsDialog } from "@/components/settings/SettingsDialog";

/** Renders the router's current search string so tests can assert URL sync
 *  (MemoryRouter does not touch window.location). */
function LocationProbe() {
  const { search } = useLocation();
  return <span data-testid="location-probe">{search}</span>;
}

const API = "http://localhost:8000/api";

function renderDialog(initialEntry = "/") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <SettingsDialog />
    </MemoryRouter>
  );
}

beforeEach(() => {
  useSettingsModalStore.getState().reset();
});

afterEach(() => {
  cleanup();
  useSettingsModalStore.getState().reset();
});

describe("SettingsDialog", () => {
  it("renders nothing while closed", () => {
    renderDialog();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("opens on the requested section with a tablist and loads provider settings", async () => {
    let providerFetches = 0;
    server.use(
      http.get(`${API}/settings/provider`, () => {
        providerFetches += 1;
        return HttpResponse.json({
          profile: "external_ollama",
          llm_provider_type: "ollama",
          llm_base_url: "http://localhost:11434",
          llm_model: "ollama_chat/llama3.1",
          mem0_embedder_model: "nomic-embed-text:latest",
          mem0_embedder_dimensions: 768,
          api_key_set: false,
          source: "database",
        });
      })
    );

    useSettingsModalStore.getState().openSettings("providers");
    renderDialog();

    const dialog = screen.getByRole("dialog", { name: "Settings" });
    expect(dialog).toBeInTheDocument();
    expect(screen.getByRole("tablist", { name: /settings/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /account/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /providers/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /appearance/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /providers/i })).toHaveAttribute(
      "aria-selected",
      "true"
    );
    expect(await screen.findByLabelText(/base url/i)).toBeInTheDocument();
    expect(screen.getByTestId("settings-section-body")).toHaveClass(
      "overflow-y-auto"
    );
    expect(providerFetches).toBe(1);
  });

  it("switches to the Account tab on click", async () => {
    const user = userEvent.setup();
    useSettingsModalStore.getState().openSettings("providers");
    renderDialog();

    await user.click(screen.getByRole("tab", { name: /account/i }));

    expect(
      await screen.findByLabelText(/current password/i)
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /account/i })).toHaveAttribute(
      "aria-selected",
      "true"
    );
  });

  it("preserves provider form state while visiting other tabs (keep-alive)", async () => {
    const user = userEvent.setup();
    useSettingsModalStore.getState().openSettings("providers");
    renderDialog();

    const baseUrl = await screen.findByLabelText(/base url/i);
    await user.clear(baseUrl);
    await user.type(baseUrl, "http://custom-host:1234");

    await user.click(screen.getByRole("tab", { name: /appearance/i }));
    expect(screen.getByRole("radio", { name: /dark/i })).toBeChecked();

    await user.click(screen.getByRole("tab", { name: /providers/i }));
    expect(screen.getByLabelText(/base url/i)).toHaveValue(
      "http://custom-host:1234"
    );
  });

  it("closes on the dialog Escape key", async () => {
    const user = userEvent.setup();
    useSettingsModalStore.getState().openSettings("account");
    renderDialog();

    await user.keyboard("{Escape}");

    expect(useSettingsModalStore.getState().open).toBe(false);
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    );
  });

  it("opens on the section given via the ?section= deep link", async () => {
    renderDialog("/settings?section=providers");

    expect(
      await screen.findByLabelText(/base url/i)
    ).toBeInTheDocument();
    expect(useSettingsModalStore.getState().open).toBe(true);
    expect(useSettingsModalStore.getState().section).toBe("providers");
  });

  it("opens on the default section for an unknown ?section= value", () => {
    renderDialog("/?section=bogus");

    expect(useSettingsModalStore.getState().open).toBe(true);
    expect(useSettingsModalStore.getState().section).toBe("account");
  });

  it("mirrors open state to the URL as ?section=…", async () => {
    useSettingsModalStore.getState().openSettings("providers");
    render(<MemoryRouter initialEntries={["/"]}>
      <LocationProbe />
      <SettingsDialog />
    </MemoryRouter>);

    await screen.findByRole("dialog", { name: "Settings" });
    await waitFor(() =>
      expect(screen.getByTestId("location-probe").textContent).toContain(
        "section=providers"
      )
    );
  });

  it("removes the ?section= param when the dialog closes", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/settings?section=providers"]}>
        <LocationProbe />
        <SettingsDialog />
      </MemoryRouter>
    );
    await screen.findByLabelText(/base url/i);

    await user.keyboard("{Escape}");

    await waitFor(() =>
      expect(useSettingsModalStore.getState().open).toBe(false)
    );
    await waitFor(() =>
      expect(screen.getByTestId("location-probe").textContent).not.toContain(
        "section="
      )
    );
  });
});