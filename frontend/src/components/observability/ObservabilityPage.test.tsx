import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { server } from "@/test/mocks/server";
import { mockConversationSummary } from "@/test/mocks/handlers";
import ObservabilityPage from "./ObservabilityPage";

const API = "http://localhost:8000/api";

beforeEach(() => {
    // Reset handlers to defaults
    server.resetHandlers();
});

function renderObsPage(canvasId: string) {
    return render(
        <MemoryRouter initialEntries={[`/observability/${canvasId}`]}>
            <Routes>
                <Route path="/observability/:canvas_id" element={<ObservabilityPage />} />
                <Route path="/chat/:conversation_id" element={<div data-testid="chat-page" />} />
                <Route path="/chat/empty" element={<div data-testid="chat-empty" />} />
                <Route path="/canvas/:canvas_id" element={<div data-testid="canvas-page" />} />
                <Route path="/" element={<div data-testid="home-page" />} />
            </Routes>
        </MemoryRouter>
    );
}

describe.skip("ObservabilityPage", () => {
    it("renders the page with canvas name", async () => {
        server.use(
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas" })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([])
            )
        );

        renderObsPage("canvas-1");

        await waitFor(() => {
            expect(screen.getByText("My Canvas")).toBeInTheDocument();
        });
        expect(screen.getByText("Observability")).toBeInTheDocument();
    });

    it("renders sidebar navigation links", async () => {
        server.use(
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas" })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([])
            )
        );

        renderObsPage("canvas-1");

        await waitFor(() => {
            expect(screen.getByText("Visual Canvas")).toBeInTheDocument();
            expect(screen.getByText("Agent Chat")).toBeInTheDocument();
        });
    });

    it("renders MLflow iframe", async () => {
        server.use(
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas" })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([])
            )
        );

        renderObsPage("canvas-1");

        await waitFor(() => {
            const iframe = screen.getByTitle("MLflow Observability Traces");
            expect(iframe).toBeInTheDocument();
            expect(iframe).toHaveAttribute("src", "/mlflow/");
        });
    });

    it("renders Full Screen link to MLflow", async () => {
        server.use(
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas" })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([])
            )
        );

        renderObsPage("canvas-1");

        await waitFor(() => {
            const fullScreenLink = screen.getByText("Full Screen");
            expect(fullScreenLink).toBeInTheDocument();
            expect(fullScreenLink.closest("a")).toHaveAttribute("href", "/mlflow/");
        });
    });

    it("renders observability info cards", async () => {
        server.use(
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas" })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([])
            )
        );

        renderObsPage("canvas-1");

        await waitFor(() => {
            expect(screen.getByText("MLflow Tracing")).toBeInTheDocument();
            expect(screen.getByText("Latency & Tokens")).toBeInTheDocument();
        });
    });

    it("navigates to existing chat when Agent Chat is clicked", async () => {
        const user = userEvent.setup();
        server.use(
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas" })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([mockConversationSummary({ id: "conv-1", name: "Test Chat" })])
            )
        );

        renderObsPage("canvas-1");

        await waitFor(() => {
            expect(screen.getByText("Agent Chat")).toBeInTheDocument();
        });

        await user.click(screen.getByText("Agent Chat"));

        await waitFor(() => {
            expect(screen.getByTestId("chat-page")).toBeInTheDocument();
        });
    });

    it("creates new conversation when Agent Chat is clicked and no conversations exist", async () => {
        const user = userEvent.setup();
        server.use(
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas" })
            ),
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

        renderObsPage("canvas-1");

        await waitFor(() => {
            expect(screen.getByText("Agent Chat")).toBeInTheDocument();
        });

        await user.click(screen.getByText("Agent Chat"));

        await waitFor(() => {
            expect(screen.getByTestId("chat-page")).toBeInTheDocument();
        });
    });

    it("handles API failure gracefully when loading canvas metadata", async () => {
        const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => { });
        server.use(
            http.get(`${API}/canvases/canvas-1`, () =>
                new HttpResponse(null, { status: 500 })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                new HttpResponse(null, { status: 500 })
            )
        );

        renderObsPage("canvas-1");

        await waitFor(() => {
            expect(consoleSpy).toHaveBeenCalled();
        });

        consoleSpy.mockRestore();
    });

    it("renders sidebar footer with MLflow branding", async () => {
        server.use(
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas" })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([])
            )
        );

        renderObsPage("canvas-1");

        await waitFor(() => {
            expect(screen.getByText("Powered by MLflow")).toBeInTheDocument();
        });
    });

    it("renders Home link in sidebar header", async () => {
        server.use(
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas" })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([])
            )
        );

        renderObsPage("canvas-1");

        await waitFor(() => {
            expect(screen.getByTitle("Home")).toBeInTheDocument();
        });
    });
});
