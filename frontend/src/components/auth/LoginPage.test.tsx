import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "@/test/mocks/server";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import LoginPage from "./LoginPage";

const API = "http://localhost:8000/api";

const mockUser = {
  id: "user-1",
  email: "tester@example.com",
  created_at: "2024-01-01T00:00:00Z",
};

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<div data-testid="register-page" />} />
        <Route path="/" element={<div data-testid="home" />} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  useAuthStore.getState().reset();
});

describe("LoginPage", () => {
  it("renders email and password inputs and a submit button", () => {
    renderAt("/login");
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /log in/i })).toBeInTheDocument();
  });

  it("links to the register page", async () => {
    const user = userEvent.setup();
    renderAt("/login");
    await user.click(screen.getByRole("link", { name: /register/i }));
    expect(screen.getByTestId("register-page")).toBeInTheDocument();
  });

  it("disables submit and shows loading state while submitting", async () => {
    server.use(
      http.post(`${API}/auth/login`, async () => {
        await new Promise((r) => setTimeout(r, 50));
        return HttpResponse.json({ user: mockUser });
      })
    );
    const user = userEvent.setup();
    renderAt("/login");
    await user.type(screen.getByLabelText(/email/i), "tester@example.com");
    await user.type(screen.getByLabelText(/password/i), "supersecret");
    await user.click(screen.getByRole("button", { name: /log in/i }));
    // While the request is in flight the button is disabled / shows loading
    expect(await screen.findByRole("button", { name: /logging in/i })).toBeDisabled();
    await waitFor(() => {
      expect(useAuthStore.getState().user).toEqual(mockUser);
    });
  });

  it("logs in, hydrates the auth store, and navigates to the app", async () => {
    server.use(
      http.post(`${API}/auth/login`, () => HttpResponse.json({ user: mockUser }))
    );
    const user = userEvent.setup();
    renderAt("/login");
    await user.type(screen.getByLabelText(/email/i), "tester@example.com");
    await user.type(screen.getByLabelText(/password/i), "supersecret");
    await user.click(screen.getByRole("button", { name: /log in/i }));

    await waitFor(() => {
      expect(useAuthStore.getState().status).toBe("authenticated");
      expect(useAuthStore.getState().user).toEqual(mockUser);
    });
    expect(screen.getByTestId("home")).toBeInTheDocument();
  });

  it("shows the server error detail when credentials are invalid", async () => {
    server.use(
      http.post(`${API}/auth/login`, () =>
        HttpResponse.json({ detail: "Invalid email or password." }, { status: 401 })
      )
    );
    const user = userEvent.setup();
    renderAt("/login");
    await user.type(screen.getByLabelText(/email/i), "tester@example.com");
    await user.type(screen.getByLabelText(/password/i), "wrong");
    await user.click(screen.getByRole("button", { name: /log in/i }));

    await waitFor(() => {
      expect(screen.getByText(/Invalid email or password/i)).toBeInTheDocument();
    });
    expect(useAuthStore.getState().status).not.toBe("authenticated");
    expect(screen.queryByTestId("home")).not.toBeInTheDocument();
  });
});