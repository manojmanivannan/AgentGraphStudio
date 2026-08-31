import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { useAuthStore } from "@/store/authStore";
import { useSettingsModalStore } from "@/store/settingsModalStore";
import { server } from "@/test/mocks/server";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AccountControls } from "./AccountControls";

const API = "http://localhost:8000/api";

const mockUser = {
  id: "user-1",
  email: "tester@example.com",
  created_at: "2024-01-01T00:00:00Z",
};

function renderControls(initialEntry = "/") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/" element={<AccountControls />} />
        <Route path="/account" element={<div data-testid="account-page" />} />
        <Route path="/login" element={<div data-testid="login-page" />} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  useAuthStore.getState().reset();
  server.resetHandlers();
});

describe("AccountControls", () => {
  it("renders the theme toggle even when no user is logged in", () => {
    renderControls();
    expect(screen.getByTestId("theme-toggle")).toBeInTheDocument();
    // No account cluster when unauthenticated.
    expect(screen.queryByTestId("logout-button")).not.toBeInTheDocument();
    expect(screen.queryByTestId("settings-button")).not.toBeInTheDocument();
  });

  it("renders the logged-in user's email, settings button, and logout button", () => {
    useAuthStore.getState().setUser(mockUser);
    renderControls();

    expect(screen.getByText(/tester@example\.com/)).toBeInTheDocument();
    expect(screen.getByTestId("settings-button")).toBeInTheDocument();
    expect(screen.getByTestId("logout-button")).toBeInTheDocument();
  });

  it("opens the settings dialog on the account section without navigating", async () => {
    const user = userEvent.setup();
    useAuthStore.getState().setUser(mockUser);
    useSettingsModalStore.getState().reset();
    renderControls();

    await user.click(screen.getByTestId("settings-button"));

    expect(useSettingsModalStore.getState().open).toBe(true);
    expect(useSettingsModalStore.getState().section).toBe("account");
    // Opening settings is an in-place overlay — no route change happened.
    expect(screen.queryByTestId("account-page")).not.toBeInTheDocument();
  });

  it("calls the backend logout endpoint, clears the auth store, and navigates to /login", async () => {
    const user = userEvent.setup();
    useAuthStore.getState().setUser(mockUser);

    let logoutCalled = false;
    server.use(
      http.post(`${API}/auth/logout`, () => {
        logoutCalled = true;
        return HttpResponse.json({ ok: true });
      })
    );

    renderControls();

    await user.click(screen.getByTestId("logout-button"));

    await waitFor(() => {
      expect(logoutCalled).toBe(true);
    });
    await waitFor(() => {
      expect(useAuthStore.getState().status).toBe("unauthenticated");
      expect(useAuthStore.getState().user).toBeNull();
    });
    expect(screen.getByTestId("login-page")).toBeInTheDocument();
  });

  it("still clears the auth store and navigates to /login even if the backend logout call fails", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const user = userEvent.setup();
    useAuthStore.getState().setUser(mockUser);

    server.use(
      http.post(`${API}/auth/logout`, () => new HttpResponse(null, { status: 500 }))
    );

    renderControls();

    await user.click(screen.getByTestId("logout-button"));

    await waitFor(() => {
      expect(useAuthStore.getState().status).toBe("unauthenticated");
    });
    expect(useAuthStore.getState().user).toBeNull();
    expect(screen.getByTestId("login-page")).toBeInTheDocument();
    consoleSpy.mockRestore();
  });
});