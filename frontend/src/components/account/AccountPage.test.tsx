import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "@/test/mocks/server";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import AccountPage from "./AccountPage";

const API = "http://localhost:8000/api";

const mockUser = {
  id: "user-1",
  email: "tester@example.com",
  created_at: "2024-01-01T00:00:00Z",
};

function renderAt(path = "/account") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/account" element={<AccountPage />} />
        <Route path="/" element={<div data-testid="home" />} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  useAuthStore.setState({ user: mockUser, status: "authenticated" });
});

describe("AccountPage", () => {
  it("renders the current user's email and the change-password + logout-others controls", () => {
    renderAt();
    expect(screen.getByText(/tester@example.com/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/current password/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^new password$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/confirm new password/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /change password/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /log out other sessions/i })
    ).toBeInTheDocument();
  });

  it("shows a client-side error when the new passwords do not match", async () => {
    const user = userEvent.setup();
    renderAt();
    await user.type(screen.getByLabelText(/current password/i), "old-secret-123");
    await user.type(screen.getByLabelText(/^new password$/i), "new-secret-456");
    await user.type(
      screen.getByLabelText(/confirm new password/i),
      "different-secret-789"
    );
    await user.click(screen.getByRole("button", { name: /change password/i }));

    await waitFor(() => {
      expect(screen.getByText(/passwords do not match/i)).toBeInTheDocument();
    });
  });

  it("changes the password and shows a success message", async () => {
    let captured: { current_password: string; new_password: string } | null = null;
    server.use(
      http.post(`${API}/auth/change-password`, async ({ request }) => {
        captured = (await request.json()) as {
          current_password: string;
          new_password: string;
        };
        return HttpResponse.json({ ok: true });
      })
    );
    const user = userEvent.setup();
    renderAt();
    await user.type(screen.getByLabelText(/current password/i), "old-secret-123");
    await user.type(screen.getByLabelText(/^new password$/i), "new-secret-456");
    await user.type(screen.getByLabelText(/confirm new password/i), "new-secret-456");
    await user.click(screen.getByRole("button", { name: /change password/i }));

    await waitFor(() => {
      expect(captured).toEqual({
        current_password: "old-secret-123",
        new_password: "new-secret-456",
      });
    });
    await waitFor(() => {
      expect(screen.getByText(/password changed/i)).toBeInTheDocument();
    });
    // Form resets after success.
    expect(screen.getByLabelText(/current password/i)).toHaveValue("");
  });

  it("shows the server error detail when the current password is wrong (422)", async () => {
    server.use(
      http.post(
        `${API}/auth/change-password`,
        () => HttpResponse.json({ detail: "Current password is incorrect." }, { status: 422 }),
        { once: true }
      )
    );
    const user = userEvent.setup();
    renderAt();
    await user.type(screen.getByLabelText(/current password/i), "wrong-current");
    await user.type(screen.getByLabelText(/^new password$/i), "new-secret-456");
    await user.type(screen.getByLabelText(/confirm new password/i), "new-secret-456");
    await user.click(screen.getByRole("button", { name: /change password/i }));

    await waitFor(() => {
      expect(screen.getByText(/current password is incorrect/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/password changed/i)).not.toBeInTheDocument();
  });

  it("logs out other sessions and shows the revoked count", async () => {
    server.use(
      http.post(`${API}/auth/logout-other-sessions`, () =>
        HttpResponse.json({ revoked: 3 })
      )
    );
    const user = userEvent.setup();
    renderAt();
    await user.click(screen.getByRole("button", { name: /log out other sessions/i }));

    await waitFor(() => {
      expect(screen.getByText(/3 .*session/i)).toBeInTheDocument();
    });
  });

  it("disables the change-password button while submitting", async () => {
    let resolveChange!: () => void;
    const inFlight = new Promise<void>((r) => {
      resolveChange = r;
    });
    server.use(
      http.post(`${API}/auth/change-password`, async () => {
        await inFlight;
        return HttpResponse.json({ ok: true });
      })
    );
    const user = userEvent.setup();
    renderAt();
    await user.type(screen.getByLabelText(/current password/i), "old-secret-123");
    await user.type(screen.getByLabelText(/^new password$/i), "new-secret-456");
    await user.type(screen.getByLabelText(/confirm new password/i), "new-secret-456");
    await user.click(screen.getByRole("button", { name: /change password/i }));
    // While in flight, the button is disabled / shows the working state.
    expect(
      await screen.findByRole("button", { name: /changing/i })
    ).toBeDisabled();
    resolveChange();
    await waitFor(() => {
      expect(screen.getByText(/password changed/i)).toBeInTheDocument();
    });
  });
});