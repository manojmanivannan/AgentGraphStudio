import { beforeEach, describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { useCanvasStore } from "@/store/canvasStore";
import { server } from "@/test/mocks/server";
import { mockConversationSummary } from "@/test/mocks/handlers";
import { TopBar } from "./TopBar";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const API = "http://localhost:8000/api";

beforeEach(() => {
  useCanvasStore.getState().reset();
  server.resetHandlers();
});

function renderTopBar() {
  return render(
    <MemoryRouter initialEntries={["/canvas/canvas-1"]}>
      <Routes>
        <Route path="/canvas/:canvas_id" element={<TopBar />} />
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
        <TopBar />
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
});
