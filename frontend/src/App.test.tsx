import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "@/test/mocks/server";
import { mockCanvas, mockCanvasListItem } from "@/test/mocks/handlers";
import { useCanvasStore } from "@/store/canvasStore";
import App from "./App";

// AppShell contains the full ReactFlow canvas — keep App tests focused on the landing page
vi.mock("@/components/layout/AppShell", () => ({
  AppShell: () => <div data-testid="app-shell" />,
}));

beforeEach(() => {
  useCanvasStore.getState().reset();
});

describe("App — landing page", () => {
  it("renders the landing page when no canvas is open", async () => {
    server.use(http.get("http://localhost:8000/api/canvases", () => HttpResponse.json([])));

    render(<App />);

    expect(screen.getByText("Agent Builder")).toBeInTheDocument();
    expect(screen.getByText("New Canvas")).toBeInTheDocument();
  });

  it("renders AppShell when a canvas is already open in the store", () => {
    useCanvasStore.getState().setCanvas("canvas-1", "My Canvas");

    render(<App />);

    expect(screen.getByTestId("app-shell")).toBeInTheDocument();
    expect(screen.queryByText("Agent Builder")).not.toBeInTheDocument();
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

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("First Canvas")).toBeInTheDocument();
      expect(screen.getByText("Second Canvas")).toBeInTheDocument();
    });
  });

  it("shows no canvas list when API returns empty array", async () => {
    server.use(http.get("http://localhost:8000/api/canvases", () => HttpResponse.json([])));

    render(<App />);

    await waitFor(() => {
      expect(screen.queryByText("Recent Canvases")).not.toBeInTheDocument();
    });
  });

  it("creates a new canvas and navigates to AppShell on button click", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    server.use(
      http.get("http://localhost:8000/api/canvases", () => HttpResponse.json([])),
      http.post("http://localhost:8000/api/canvases", () =>
        HttpResponse.json(mockCanvas({ id: "new-canvas", name: "Untitled Canvas" }), { status: 201 })
      )
    );

    render(<App />);
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

    render(<App />);
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

    render(<App />);
    await userEvent.click(screen.getByText("New Canvas"));

    await waitFor(() => {
      expect(consoleSpy).toHaveBeenCalledWith(
        "Failed to create canvas:",
        expect.any(Error)
      );
    });

    expect(screen.getByText("Agent Builder")).toBeInTheDocument(); // stays on landing
    consoleSpy.mockRestore();
  });
});
