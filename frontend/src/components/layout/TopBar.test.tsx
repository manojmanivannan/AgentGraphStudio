import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { useCanvasStore } from "@/store/canvasStore";
import { useCanvasHistoryStore } from "@/store/canvasHistoryStore";
import { useAuthStore } from "@/store/authStore";
import { server } from "@/test/mocks/server";
import { mockConversationSummary } from "@/test/mocks/handlers";
import { TopBar } from "./TopBar";
import { SidebarRail } from "./SidebarRail";
import { UnsavedChangesDialogHost } from "@/components/ui/UnsavedChangesDialogHost";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const API = "http://localhost:8000/api";

const mockUser = {
  id: "user-1",
  email: "tester@example.com",
  created_at: "2024-01-01T00:00:00Z",
};

beforeEach(() => {
  useCanvasStore.getState().reset();
  useAuthStore.getState().reset();
  useCanvasHistoryStore.setState({ past: [], future: [], applying: false });
  server.resetHandlers();
});

function renderTopBar() {
  return render(
    <MemoryRouter initialEntries={["/canvas/canvas-1"]}>
      <Routes>
        <Route
          path="/canvas/:canvas_id"
          element={
            <div>
              <TopBar />
              <SidebarRail />
            </div>
          }
        />
        <Route path="/chat/:conversation_id" element={<div data-testid="chat-page" />} />
        <Route path="/" element={<div data-testid="home-page" />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("TopBar", () => {
  it("renders the canvas name and handles reset on home button click", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setCanvas("canvas-test-id", "Mock Canvas Name");

    render(
      <MemoryRouter>
        <TopBar />
      </MemoryRouter>
    );

    expect(screen.getByDisplayValue("Mock Canvas Name")).toBeInTheDocument();

    const homeButton = screen.getByTestId("home-button");
    expect(homeButton).toBeInTheDocument();

    await user.click(homeButton);

    expect(useCanvasStore.getState().canvasId).toBeNull();
  });

  it("renders save status as 'Saved' when saveStatus is 'saved'", () => {
    useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");
    useCanvasStore.setState({ saveStatus: "saved" });

    render(
      <MemoryRouter>
        <TopBar />
      </MemoryRouter>
    );

    expect(screen.getByText("Saved")).toBeInTheDocument();
  });

  it("renders save status as 'Saving…' when saveStatus is 'saving'", () => {
    useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");
    useCanvasStore.setState({ saveStatus: "saving" });

    render(
      <MemoryRouter>
        <TopBar />
      </MemoryRouter>
    );

    expect(screen.getByText("Saving…")).toBeInTheDocument();
  });

  it("renders save status as 'Save failed' when saveStatus is 'error'", () => {
    useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");
    useCanvasStore.setState({ saveStatus: "error" });

    render(
      <MemoryRouter>
        <TopBar />
      </MemoryRouter>
    );

    expect(screen.getByText("Save failed")).toBeInTheDocument();
  });

  it("updates canvas name when typed in input", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setCanvas("canvas-1", "Old Name");

    render(
      <MemoryRouter>
        <TopBar />
      </MemoryRouter>
    );

    const input = screen.getByTestId("canvas-name-input");
    await user.clear(input);
    await user.type(input, "New Name");

    expect(useCanvasStore.getState().canvasName).toBe("New Name");
  });

  it("navigates to existing chat when chat button is clicked", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");

    server.use(
      http.get(`${API}/canvases/canvas-1/conversations`, () =>
        HttpResponse.json([mockConversationSummary({ id: "conv-1", name: "Test Chat" })])
      )
    );

    renderTopBar();

    const chatButton = screen.getByTestId("chat-toggle");
    await user.click(chatButton);

    await waitFor(() => {
      expect(screen.getByTestId("chat-page")).toBeInTheDocument();
    });
  });

  it("creates new conversation when chat button clicked and no conversations exist", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");

    server.use(
      http.get(`${API}/canvases/canvas-1/conversations`, () =>
        HttpResponse.json([])
      ),
      http.post(`${API}/canvases/canvas-1/conversations`, () =>
        HttpResponse.json(
          { id: "conv-new", canvas_id: "canvas-1", name: "New Conversation" },
          { status: 201 }
        )
      )
    );

    renderTopBar();

    const chatButton = screen.getByTestId("chat-toggle");
    await user.click(chatButton);

    await waitFor(() => {
      expect(screen.getByTestId("chat-page")).toBeInTheDocument();
    });
  });

  it("renders observability button", () => {
    useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");

    render(
      <MemoryRouter>
        <SidebarRail />
      </MemoryRouter>
    );

    expect(screen.getByTestId("observability-toggle")).toBeInTheDocument();
  });

  it("shows home button", () => {
    useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");

    render(
      <MemoryRouter>
        <TopBar />
      </MemoryRouter>
    );

    expect(screen.getByTestId("home-button")).toBeInTheDocument();
  });

  it("adjusts left offset based on sidebarCollapsed state", () => {
    act(() => {
      useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");
      useCanvasStore.setState({ sidebarCollapsed: false });
    });

    const { rerender } = render(
      <MemoryRouter>
        <TopBar />
      </MemoryRouter>
    );

    const topBar = screen.getByTestId("top-bar");
    expect(topBar).toHaveStyle({ left: "256px" });

    act(() => {
      useCanvasStore.setState({ sidebarCollapsed: true });
    });
    rerender(
      <MemoryRouter>
        <TopBar />
      </MemoryRouter>
    );

    expect(topBar).toHaveStyle({ left: "64px" });
  });

  describe("logout", () => {
    it("renders a logout button showing the logged-in user's email", () => {
      useAuthStore.getState().setUser(mockUser);
      useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");

      render(
        <MemoryRouter>
          <TopBar />
        </MemoryRouter>
      );

      expect(screen.getByTestId("logout-button")).toBeInTheDocument();
      expect(screen.getByText(/tester@example\.com/)).toBeInTheDocument();
    });

    it("calls the backend logout endpoint, clears the auth store, and navigates to /login", async () => {
      const user = userEvent.setup();
      useAuthStore.getState().setUser(mockUser);
      useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");

      let logoutCalled = false;
      server.use(
        http.post(`${API}/auth/logout`, () => {
          logoutCalled = true;
          return HttpResponse.json({ ok: true });
        })
      );

      render(
        <MemoryRouter initialEntries={["/canvas/canvas-1"]}>
          <Routes>
            <Route path="/canvas/:canvas_id" element={<TopBar />} />
            <Route path="/login" element={<div data-testid="login-page" />} />
          </Routes>
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
      expect(screen.getByTestId("login-page")).toBeInTheDocument();
    });

    it("still clears the auth store and navigates to /login even if the backend logout call fails", async () => {
      const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
      const user = userEvent.setup();
      useAuthStore.getState().setUser(mockUser);
      useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");

      server.use(
        http.post(`${API}/auth/logout`, () => new HttpResponse(null, { status: 500 }))
      );

      render(
        <MemoryRouter initialEntries={["/canvas/canvas-1"]}>
          <Routes>
            <Route path="/canvas/:canvas_id" element={<TopBar />} />
            <Route path="/login" element={<div data-testid="login-page" />} />
          </Routes>
        </MemoryRouter>
      );

      await user.click(screen.getByTestId("logout-button"));

      await waitFor(() => {
        expect(useAuthStore.getState().status).toBe("unauthenticated");
      });
      expect(screen.getByTestId("login-page")).toBeInTheDocument();
      consoleSpy.mockRestore();
    });
  });

  describe("Save button", () => {
    it("is disabled when the canvas has no unsaved changes", () => {
      useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");

      render(
        <MemoryRouter>
          <TopBar />
        </MemoryRouter>
      );

      expect(screen.getByTestId("save-button")).toBeDisabled();
    });

    it("enables once the canvas becomes dirty, saves on click, and clears the dirty flag", async () => {
      const user = userEvent.setup();
      useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");
      useCanvasStore.getState().setNodes([
        { id: "n1", type: "agent", position: { x: 0, y: 0 }, data: {} },
      ] as any);
      expect(useCanvasStore.getState().isDirty).toBe(true);

      server.use(
        http.put(`${API}/canvases/canvas-1`, () =>
          HttpResponse.json({
            id: "canvas-1",
            name: "Test Canvas",
            nodes: { agents: [], tools: [] },
            edges: [],
            created_at: "",
            updated_at: "",
          })
        )
      );

      render(
        <MemoryRouter>
          <TopBar />
        </MemoryRouter>
      );

      const saveButton = screen.getByTestId("save-button");
      expect(saveButton).not.toBeDisabled();
      expect(screen.getByText("Unsaved changes")).toBeInTheDocument();

      await user.click(saveButton);

      await waitFor(() => {
        expect(useCanvasStore.getState().isDirty).toBe(false);
      });
      await waitFor(() => {
        expect(screen.getByTestId("save-button")).toBeDisabled();
      });
    });
  });

  describe("Undo/Redo buttons", () => {
    it("are disabled when there is no history", () => {
      useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");

      render(
        <MemoryRouter>
          <TopBar />
        </MemoryRouter>
      );

      expect(screen.getByTestId("undo-button")).toBeDisabled();
      expect(screen.getByTestId("redo-button")).toBeDisabled();
    });

    it("undo restores the previous snapshot and enables redo", async () => {
      const user = userEvent.setup();
      useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");
      useCanvasHistoryStore.setState({
        past: [{ nodes: [], edges: [] }],
        future: [],
        applying: false,
      });

      render(
        <MemoryRouter>
          <TopBar />
        </MemoryRouter>
      );

      const undoButton = screen.getByTestId("undo-button");
      expect(undoButton).not.toBeDisabled();
      expect(screen.getByTestId("redo-button")).toBeDisabled();

      await user.click(undoButton);

      expect(useCanvasHistoryStore.getState().past).toHaveLength(0);
      expect(useCanvasHistoryStore.getState().future).toHaveLength(1);
      await waitFor(() => {
        expect(screen.getByTestId("redo-button")).not.toBeDisabled();
      });
    });

    it("redo re-applies an undone change", async () => {
      const user = userEvent.setup();
      useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");
      useCanvasHistoryStore.setState({
        past: [],
        future: [{ nodes: [], edges: [] }],
        applying: false,
      });

      render(
        <MemoryRouter>
          <TopBar />
        </MemoryRouter>
      );

      const redoButton = screen.getByTestId("redo-button");
      expect(redoButton).not.toBeDisabled();

      await user.click(redoButton);

      expect(useCanvasHistoryStore.getState().future).toHaveLength(0);
      expect(useCanvasHistoryStore.getState().past).toHaveLength(1);
    });
  });

  describe("unsaved changes guard on Home button", () => {
    it("navigates home immediately when there are no unsaved changes", async () => {
      const user = userEvent.setup();
      useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");

      render(
        <MemoryRouter>
          <TopBar />
        </MemoryRouter>
      );

      await user.click(screen.getByTestId("home-button"));

      expect(useCanvasStore.getState().canvasId).toBeNull();
    });

    it("shows a save/discard/cancel dialog before discarding unsaved changes", async () => {
      const user = userEvent.setup();
      useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");
      useCanvasStore.getState().setNodes([
        { id: "n1", type: "agent", position: { x: 0, y: 0 }, data: {} },
      ] as any);

      render(
        <MemoryRouter>
          <TopBar />
          <UnsavedChangesDialogHost />
        </MemoryRouter>
      );

      await user.click(screen.getByTestId("home-button"));

      expect(await screen.findByRole("dialog")).toHaveTextContent("Unsaved changes");
      expect(useCanvasStore.getState().canvasId).toBe("canvas-1");

      await user.click(screen.getByRole("button", { name: "Discard changes" }));

      await waitFor(() => {
        expect(useCanvasStore.getState().canvasId).toBeNull();
      });
    });

    it("keeps the canvas open when the dialog is cancelled", async () => {
      const user = userEvent.setup();
      useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");
      useCanvasStore.getState().setNodes([
        { id: "n1", type: "agent", position: { x: 0, y: 0 }, data: {} },
      ] as any);

      render(
        <MemoryRouter>
          <TopBar />
          <UnsavedChangesDialogHost />
        </MemoryRouter>
      );

      await user.click(screen.getByTestId("home-button"));
      await screen.findByRole("dialog");
      await user.click(screen.getByRole("button", { name: "Cancel" }));

      expect(useCanvasStore.getState().canvasId).toBe("canvas-1");
    });

    it("saves then navigates home when Save & continue is chosen", async () => {
      const user = userEvent.setup();
      useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");
      useCanvasStore.getState().setNodes([
        { id: "n1", type: "agent", position: { x: 0, y: 0 }, data: {} },
      ] as any);

      server.use(
        http.put(`${API}/canvases/canvas-1`, () =>
          HttpResponse.json({
            id: "canvas-1",
            name: "Test Canvas",
            nodes: { agents: [], tools: [] },
            edges: [],
            created_at: "",
            updated_at: "",
          })
        )
      );

      render(
        <MemoryRouter>
          <TopBar />
          <UnsavedChangesDialogHost />
        </MemoryRouter>
      );

      await user.click(screen.getByTestId("home-button"));
      await screen.findByRole("dialog");
      await user.click(screen.getByRole("button", { name: "Save & continue" }));

      await waitFor(() => {
        expect(useCanvasStore.getState().canvasId).toBeNull();
      });
    });
  });
});
