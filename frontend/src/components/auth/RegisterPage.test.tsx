import { beforeEach, describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "@/test/mocks/server";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import RegisterPage from "./RegisterPage";

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
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/login" element={<div data-testid="login-page" />} />
        <Route path="/" element={<div data-testid="home" />} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  useAuthStore.getState().reset();
});

describe("RegisterPage", () => {
  it("renders email, password, and confirm-password inputs and a submit button", () => {
    renderAt("/register");
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^password$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/confirm password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create account|register/i })).toBeInTheDocument();
  });

  it("links to the login page", async () => {
    const user = userEvent.setup();
    renderAt("/register");
    await user.click(screen.getByRole("link", { name: /log in/i }));
    expect(screen.getByTestId("login-page")).toBeInTheDocument();
  });

  it("registers, hydrates the auth store, and navigates to the app", async () => {
    server.use(
      http.post(`${API}/auth/register`, () =>
        HttpResponse.json({ user: mockUser }, { status: 201 })
      )
    );
    const user = userEvent.setup();
    renderAt("/register");
    await user.type(screen.getByLabelText(/email/i), "tester@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "supersecret");
    await user.type(screen.getByLabelText(/confirm password/i), "supersecret");
    await user.click(screen.getByRole("button", { name: /create account|register/i }));

    await waitFor(() => {
      expect(useAuthStore.getState().status).toBe("authenticated");
      expect(useAuthStore.getState().user).toEqual(mockUser);
    });
    expect(screen.getByTestId("home")).toBeInTheDocument();
  });

  it("shows an error when passwords do not match (client-side)", async () => {
    const user = userEvent.setup();
    renderAt("/register");
    await user.type(screen.getByLabelText(/email/i), "tester@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "supersecret");
    await user.type(screen.getByLabelText(/confirm password/i), "different");
    await user.click(screen.getByRole("button", { name: /create account|register/i }));

    await waitFor(() => {
      expect(screen.getByText(/passwords do not match/i)).toBeInTheDocument();
    });
    expect(useAuthStore.getState().status).not.toBe("authenticated");
  });

  it("shows the server error detail when the email is already registered", async () => {
    server.use(
      http.post(`${API}/auth/register`, () =>
        HttpResponse.json({ detail: "Email already registered." }, { status: 409 })
      )
    );
    const user = userEvent.setup();
    renderAt("/register");
    await user.type(screen.getByLabelText(/email/i), "tester@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "supersecret");
    await user.type(screen.getByLabelText(/confirm password/i), "supersecret");
    await user.click(screen.getByRole("button", { name: /create account|register/i }));

    await waitFor(() => {
      expect(screen.getByText(/Email already registered/i)).toBeInTheDocument();
    });
    expect(useAuthStore.getState().status).not.toBe("authenticated");
  });
});