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

    expect(screen.getByText("AgentGraph Studio")).toBeInTheDocument();
    expect(screen.getByText("New Canvas")).toBeInTheDocument();
  });

  it("renders AppShell when a canvas is already open in the store", () => {
    useCanvasStore.getState().setCanvas("canvas-1", "My Canvas");

    render(<App />);

    expect(screen.getByTestId("app-shell")).toBeInTheDocument();
    expect(screen.queryByText("AgentGraph Studio")).not.toBeInTheDocument();
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

  it("shows empty state when API returns empty array", async () => {
    server.use(http.get("http://localhost:8000/api/canvases", () => HttpResponse.json([])));

    render(<App />);

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

    render(<App />);

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

    render(<App />);

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

    render(<App />);

    // Trigger input file change using the test id
    const file = new File(["dummy content"], "canvas.zip", { type: "application/zip" });
    const fileInput = screen.getByTestId("file-input");
    await user.upload(fileInput, file);

    await waitFor(() => {
      expect(screen.getByTestId("app-shell")).toBeInTheDocument();
    });

    expect(useCanvasStore.getState().canvasId).toBe("imported-zip");
  });
});
