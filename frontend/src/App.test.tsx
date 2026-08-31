import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "@/test/mocks/server";
import { mockCanvas, mockCanvasListItem } from "@/test/mocks/handlers";
import { useCanvasStore } from "@/store/canvasStore";
import { useAuthStore } from "@/store/authStore";
import { useSettingsModalStore } from "@/store/settingsModalStore";
import App from "./App";
import { MemoryRouter } from "react-router-dom";

const mockUser = {
  id: "user-1",
  email: "tester@example.com",
  created_at: "2024-01-01T00:00:00Z",
};

vi.mock("@/components/layout/AppShell", () => ({
  AppShell: () => (
    <div data-testid="app-shell">
      <div data-testid="conversation-replay-panel" />
    </div>
  ),
}));
vi.mock("@/components/chat/ChatPage", () => ({
  default: () => <div data-testid="chat-page" />,
}));

beforeEach(() => {
  useCanvasStore.getState().reset();
  // Existing App tests assume an authenticated session so the route guard
  // lets them straight through to the landing page / canvas editor without
  // waiting on the async /auth/me hydration.
  useAuthStore.getState().setUser(mockUser);
  // Clear the JSDOM URL query params between tests to avoid test pollution
  window.history.replaceState({}, "", "/");
});

describe("App — landing page", () => {
  it("renders the landing page when no canvas is open", async () => {
    server.use(http.get("http://localhost:8000/api/canvases", () => HttpResponse.json([])));

    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    );

    expect(screen.getByText("AgentGraph Studio")).toBeInTheDocument();
    expect(screen.getByText("New Canvas")).toBeInTheDocument();
  });

  it("renders AppShell when a canvas is already open in the store", async () => {
    useCanvasStore.getState().setCanvas("canvas-1", "My Canvas");

    render(
      <MemoryRouter initialEntries={["/canvas/canvas-1"]}>
        <App />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("app-shell")).toBeInTheDocument();
    });
    expect(screen.queryByText("AgentGraph Studio")).not.toBeInTheDocument();
  });

  it("shows conversation replay panel on canvas route", async () => {
    useCanvasStore.getState().setCanvas("canvas-1", "My Canvas");

    render(
      <MemoryRouter initialEntries={["/canvas/canvas-1"]}>
        <App />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("conversation-replay-panel")).toBeInTheDocument();
    });
  });

  it("lists canvases returned by the API", async () => {
    server.use(
      http.get("http://localhost:8000/api/canvases", () =>
        HttpResponse.json([
          mockCanvasListItem({ id: "c1", name: "First Canvas" }),
          mockCanvasListItem({ id: "c2", name: "Second Canvas" }),
        ])
      )
    );

    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("First Canvas")).toBeInTheDocument();
      expect(screen.getByText("Second Canvas")).toBeInTheDocument();
    });
  });

  it("shows empty state when API returns empty array", async () => {
    server.use(http.get("http://localhost:8000/api/canvases", () => HttpResponse.json([])));

    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText(/No canvases created yet/)).toBeInTheDocument();
    });
  });

  it("creates a new canvas and navigates to AppShell on button click", async () => {
    server.use(
      http.get("http://localhost:8000/api/canvases", () => HttpResponse.json([])),
      http.post("http://localhost:8000/api/canvases", () =>
        HttpResponse.json(mockCanvas({ id: "new-canvas", name: "Untitled Canvas" }), { status: 201 })
      )
    );

    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    );
    await userEvent.click(screen.getByText("New Canvas"));

    await waitFor(() => {
      expect(screen.getByTestId("app-shell")).toBeInTheDocument();
    });

    expect(useCanvasStore.getState().canvasId).toBe("new-canvas");
  });

  it("opens an existing canvas and navigates to AppShell", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("http://localhost:8000/api/canvases", () =>
        HttpResponse.json([mockCanvasListItem({ id: "c1", name: "My Canvas" })])
      ),
      http.get("http://localhost:8000/api/canvases/c1", () =>
        HttpResponse.json(mockCanvas({ id: "c1", name: "My Canvas" }))
      )
    );

    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("My Canvas")).toBeInTheDocument());
    await user.click(screen.getByText("My Canvas"));

    await waitFor(() => {
      expect(screen.getByTestId("app-shell")).toBeInTheDocument();
    });

    expect(useCanvasStore.getState().canvasId).toBe("c1");
  });

  it("handles API failure gracefully on create canvas", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    server.use(
      http.get("http://localhost:8000/api/canvases", () => HttpResponse.json([])),
      http.post("http://localhost:8000/api/canvases", () =>
        new HttpResponse(null, { status: 500 })
      )
    );

    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    );
    await userEvent.click(screen.getByText("New Canvas"));

    await waitFor(() => {
      expect(consoleSpy).toHaveBeenCalledWith(
        "Failed to create canvas:",
        expect.any(Error)
      );
    });

    expect(screen.getByText("AgentGraph Studio")).toBeInTheDocument(); // stays on landing
    consoleSpy.mockRestore();
  });

  it("filters recent canvases list based on search query", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("http://localhost:8000/api/canvases", () =>
        HttpResponse.json([
          mockCanvasListItem({ id: "c1", name: "Alpha Canvas" }),
          mockCanvasListItem({ id: "c2", name: "Beta Canvas" }),
        ])
      )
    );

    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Alpha Canvas")).toBeInTheDocument();
      expect(screen.getByText("Beta Canvas")).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText("Search canvases...");
    await user.type(searchInput, "alpha");

    expect(screen.getByText("Alpha Canvas")).toBeInTheDocument();
    expect(screen.queryByText("Beta Canvas")).not.toBeInTheDocument();
  });

  it("handles canvas deletion with confirmation modal", async () => {
    const user = userEvent.setup();
    let deleteCalled = false;

    server.use(
      http.get("http://localhost:8000/api/canvases", () =>
        HttpResponse.json([mockCanvasListItem({ id: "c1", name: "Delete Me" })])
      ),
      http.delete("http://localhost:8000/api/canvases/c1", () => {
        deleteCalled = true;
        return new HttpResponse(null, { status: 204 });
      })
    );

    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Delete Me")).toBeInTheDocument();
    });

    const deleteButton = screen.getByTitle("Delete canvas");
    await user.click(deleteButton);

    // Verify confirmation modal is open
    expect(screen.getByText("Delete Canvas?")).toBeInTheDocument();
    expect(screen.getByText(/"Delete Me"/)).toBeInTheDocument();

    // Confirm deletion
    const confirmButton = screen.getByRole("button", { name: "Delete" });
    await user.click(confirmButton);

    await waitFor(() => {
      expect(deleteCalled).toBe(true);
    });
  });

  it("imports canvas ZIP file and opens it", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("http://localhost:8000/api/canvases", () => HttpResponse.json([])),
      http.post("http://localhost:8000/api/canvases/import-zip", () =>
        HttpResponse.json(mockCanvas({ id: "imported-zip", name: "Imported ZIP Canvas" }), { status: 201 })
      ),
      http.get("http://localhost:8000/api/canvases/imported-zip", () =>
        HttpResponse.json(mockCanvas({ id: "imported-zip", name: "Imported ZIP Canvas" }))
      )
    );

    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    );

    // Trigger input file change using the test id
    const file = new File(["dummy content"], "canvas.zip", { type: "application/zip" });
    const fileInput = screen.getByTestId("file-input");
    await user.upload(fileInput, file);

    await waitFor(() => {
      expect(screen.getByTestId("app-shell")).toBeInTheDocument();
    });

    expect(useCanvasStore.getState().canvasId).toBe("imported-zip");
  });

  it("imports canvas JSON file and opens it", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("http://localhost:8000/api/canvases", () => HttpResponse.json([])),
      http.post("http://localhost:8000/api/canvases/import", () =>
        HttpResponse.json(mockCanvas({ id: "imported-json", name: "Imported JSON Canvas" }), { status: 201 })
      ),
      http.get("http://localhost:8000/api/canvases/imported-json", () =>
        HttpResponse.json(mockCanvas({ id: "imported-json", name: "Imported JSON Canvas" }))
      )
    );

    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    );

    const file = new File(['{"name":"Imported JSON Canvas"}'], "canvas.json", { type: "application/json" });
    const fileInput = screen.getByTestId("file-input");
    await user.upload(fileInput, file);

    await waitFor(() => {
      expect(screen.getByTestId("app-shell")).toBeInTheDocument();
    });

    expect(useCanvasStore.getState().canvasId).toBe("imported-json");
  });

  it("supports multi-select mode and batch deletion", async () => {
    const user = userEvent.setup();
    const deletedIds: string[] = [];

    server.use(
      http.get("http://localhost:8000/api/canvases", () =>
        HttpResponse.json([
          mockCanvasListItem({ id: "canvas-1", name: "Canvas One" }),
          mockCanvasListItem({ id: "canvas-2", name: "Canvas Two" }),
        ])
      ),
      http.delete("http://localhost:8000/api/canvases/:id", ({ params }) => {
        deletedIds.push(params.id as string);
        return new HttpResponse(null, { status: 204 });
      })
    );

    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    );

    // Verify canvases are rendered
    await waitFor(() => {
      expect(screen.getByText("Canvas One")).toBeInTheDocument();
      expect(screen.getByText("Canvas Two")).toBeInTheDocument();
    });

    // Enter selection mode
    const selectButton = screen.getByRole("button", { name: "Select" });
    await user.click(selectButton);

    // Verify selection buttons are displayed
    expect(screen.getByRole("button", { name: "Select All" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    const deleteSelectedBtn = screen.getByRole("button", { name: /Delete Selected/ });
    expect(deleteSelectedBtn).toBeInTheDocument();
    expect(deleteSelectedBtn).toBeDisabled();

    // Select Canvas One by clicking its card
    await user.click(screen.getByText("Canvas One"));
    expect(screen.getByRole("button", { name: "Delete Selected (1)" })).toBeInTheDocument();

    // Select Canvas Two by clicking its card
    await user.click(screen.getByText("Canvas Two"));
    const finalDeleteBtn = screen.getByRole("button", { name: "Delete Selected (2)" });
    expect(finalDeleteBtn).toBeInTheDocument();
    expect(finalDeleteBtn).toBeEnabled();

    // Click Delete Selected
    await user.click(finalDeleteBtn);

    // Verify confirmation modal is open with batch title and message
    expect(screen.getByText("Delete 2 Canvases?")).toBeInTheDocument();
    expect(screen.getByText(/Are you sure you want to delete the/)).toBeInTheDocument();

    // Confirm deletion
    const confirmButton = screen.getByRole("button", { name: "Delete" });
    await user.click(confirmButton);

    // Verify both items deleted
    await waitFor(() => {
      expect(deletedIds).toContain("canvas-1");
      expect(deletedIds).toContain("canvas-2");
    });
  });

  it("toggles all visible canvases on Select All click", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("http://localhost:8000/api/canvases", () =>
        HttpResponse.json([
          mockCanvasListItem({ id: "canvas-1", name: "Canvas One" }),
          mockCanvasListItem({ id: "canvas-2", name: "Canvas Two" }),
        ])
      )
    );

    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Canvas One")).toBeInTheDocument();
    });

    // Enter selection mode
    await user.click(screen.getByRole("button", { name: "Select" }));

    // Click Select All
    await user.click(screen.getByRole("button", { name: "Select All" }));
    expect(screen.getByRole("button", { name: "Delete Selected (2)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Deselect All" })).toBeInTheDocument();

    // Click Deselect All
    await user.click(screen.getByRole("button", { name: "Deselect All" }));
    expect(screen.getByRole("button", { name: "Delete Selected (0)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Select All" })).toBeInTheDocument();
  });

  describe("landing page header — logout", () => {
    it("renders a logout button on the landing page when authenticated", async () => {
      server.use(http.get("http://localhost:8000/api/canvases", () => HttpResponse.json([])));

      render(
        <MemoryRouter initialEntries={["/"]}>
          <App />
        </MemoryRouter>
      );

      expect(screen.getByTestId("logout-button")).toBeInTheDocument();
    });

    it("does not render a logout button when not authenticated", async () => {
      useAuthStore.getState().clear();
      render(
        <MemoryRouter initialEntries={["/"]}>
          <App />
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(screen.getByText("Welcome back")).toBeInTheDocument();
      });
      expect(screen.queryByTestId("logout-button")).not.toBeInTheDocument();
    });

    it("calls the backend logout endpoint, clears the auth store, and navigates to /login", async () => {
      const user = userEvent.setup();
      let logoutCalled = false;
      server.use(
        http.get("http://localhost:8000/api/canvases", () => HttpResponse.json([])),
        http.post("http://localhost:8000/api/auth/logout", () => {
          logoutCalled = true;
          return HttpResponse.json({ ok: true });
        })
      );

      render(
        <MemoryRouter initialEntries={["/"]}>
          <App />
        </MemoryRouter>
      );

      await user.click(screen.getByTestId("logout-button"));

      await waitFor(() => {
        expect(logoutCalled).toBe(true);
      });
      await waitFor(() => {
        expect(useAuthStore.getState().status).toBe("unauthenticated");
        expect(useAuthStore.getState().user).toBeNull();
      });
      expect(screen.getByText("Welcome back")).toBeInTheDocument();
    });

    it("still clears the auth store and navigates to /login even if the backend logout call fails", async () => {
      const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
      const user = userEvent.setup();
      server.use(
        http.get("http://localhost:8000/api/canvases", () => HttpResponse.json([])),
        http.post("http://localhost:8000/api/auth/logout", () => new HttpResponse(null, { status: 500 }))
      );

      render(
        <MemoryRouter initialEntries={["/"]}>
          <App />
        </MemoryRouter>
      );

      await user.click(screen.getByTestId("logout-button"));

      await waitFor(() => {
        expect(useAuthStore.getState().status).toBe("unauthenticated");
      });
      expect(screen.getByText("Welcome back")).toBeInTheDocument();
      consoleSpy.mockRestore();
    });
  });

  it("shows Agent Chat card on the landing page if canvases are available and navigates on click", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("http://localhost:8000/api/canvases", () =>
        HttpResponse.json([
          mockCanvasListItem({ id: "c1", name: "Alpha Canvas" }),
        ])
      )
    );

    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Alpha Canvas")).toBeInTheDocument();
      expect(screen.getByText("Agent Chat")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Agent Chat"));

    await waitFor(() => {
      expect(screen.getByTestId("chat-page")).toBeInTheDocument();
    });
  });
});

describe("App — auth guards", () => {
  it("redirects unauthenticated users hitting '/' to /login", async () => {
    useAuthStore.getState().clear();
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText("Welcome back")).toBeInTheDocument();
    });
    // The landing page renders "AgentGraph Studio" as a heading; the login
    // page only has it as a small home link, so the heading should be absent.
    expect(screen.queryByRole("heading", { name: /AgentGraph Studio/i })).not.toBeInTheDocument();
  });

  it("redirects unauthenticated users hitting a canvas route to /login", async () => {
    useAuthStore.getState().clear();
    render(
      <MemoryRouter initialEntries={["/canvas/c1"]}>
        <App />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText("Welcome back")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("app-shell")).not.toBeInTheDocument();
  });

  it("redirects authenticated users hitting /login to the app", async () => {
    render(
      <MemoryRouter initialEntries={["/login"]}>
        <App />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText("AgentGraph Studio")).toBeInTheDocument();
    });
    expect(screen.queryByText("Welcome back")).not.toBeInTheDocument();
  });

  it("redirects authenticated users hitting /register to the app", async () => {
    render(
      <MemoryRouter initialEntries={["/register"]}>
        <App />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText("AgentGraph Studio")).toBeInTheDocument();
    });
    expect(screen.queryByText("Create your account")).not.toBeInTheDocument();
  });

  it("hydrates an authenticated session from /auth/me on boot", async () => {
    useAuthStore.getState().reset();
    server.use(
      http.get("http://localhost:8000/api/auth/me", () => HttpResponse.json(mockUser))
    );
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(useAuthStore.getState().status).toBe("authenticated");
      expect(screen.getByText("AgentGraph Studio")).toBeInTheDocument();
    });
  });

  it("hydrates to unauthenticated (redirects to /login) when /auth/me returns 401", async () => {
    useAuthStore.getState().reset();
    server.use(
      http.get("http://localhost:8000/api/auth/me", () => new HttpResponse(null, { status: 401 }))
    );
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(useAuthStore.getState().status).toBe("unauthenticated");
      expect(screen.getByText("Welcome back")).toBeInTheDocument();
    });
  });

  it("clears stale auth state and routes to /login when a data call returns 401", async () => {
    server.use(
      http.get("http://localhost:8000/api/canvases", () => new HttpResponse(null, { status: 401 }))
    );
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(useAuthStore.getState().status).toBe("unauthenticated");
      expect(screen.getByText("Welcome back")).toBeInTheDocument();
    });
    expect(useAuthStore.getState().user).toBeNull();
  });
});

describe("App — unified settings dialog", () => {
  beforeEach(() => {
    useSettingsModalStore.getState().reset();
  });

  it("opens the settings dialog from the landing header gear without navigating", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    );
    expect(screen.getByText("New Canvas")).toBeInTheDocument();

    await user.click(screen.getByTestId("settings-button"));

    expect(screen.getByRole("dialog", { name: "Settings" })).toBeInTheDocument();
    // The landing page stays mounted behind the dialog.
    expect(screen.getByText("New Canvas")).toBeInTheDocument();
    expect(useSettingsModalStore.getState().section).toBe("account");
  });

  it("redirects /settings to the dialog's Providers section", async () => {
    render(
      <MemoryRouter initialEntries={["/settings"]}>
        <App />
      </MemoryRouter>
    );

    expect(
      await screen.findByLabelText(/base url/i)
    ).toBeInTheDocument();
    expect(useSettingsModalStore.getState().open).toBe(true);
    expect(useSettingsModalStore.getState().section).toBe("providers");

  });

  it("redirects /account to the dialog's Account section", async () => {
    render(
      <MemoryRouter initialEntries={["/account"]}>
        <App />
      </MemoryRouter>
    );

    expect(
      await screen.findByLabelText(/current password/i)
    ).toBeInTheDocument();
    expect(useSettingsModalStore.getState().open).toBe(true);
    expect(useSettingsModalStore.getState().section).toBe("account");
  });

  it("opens the default section when the ?section= value is unknown", async () => {
    render(
      <MemoryRouter initialEntries={["/?section=bogus"]}>
        <App />
      </MemoryRouter>
    );

    expect(
      await screen.findByLabelText(/current password/i)
    ).toBeInTheDocument();
    expect(useSettingsModalStore.getState().section).toBe("account");
  });
});
