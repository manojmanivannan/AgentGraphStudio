import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useCanvasStore } from "@/store/canvasStore";
import { CanvasToolbar } from "./CanvasToolbar";
import type { CanvasSavePayload } from "@/types";

// Mock the API module — CanvasToolbar only calls importCanvas
vi.mock("@/lib/api", () => ({
  importCanvas: vi.fn().mockResolvedValue({
    id: "imported-1",
    name: "Imported Canvas",
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-01T00:00:00Z",
    nodes: {
      agents: [
        {
          id: "agent-1",
          canvas_id: "imported-1",
          name: "Agent 1",
          role: "",
          instructions: "",
          model_name: "ollama:llama3.1",
          agent_type: "worker",
          position_x: 100,
          position_y: 100,
        },
      ],
      tools: [],
    },
    edges: [],
  }),
}));

beforeEach(() => {
  useCanvasStore.getState().reset();
  useCanvasStore.getState().setCanvas("canvas-1", "My Canvas");
  vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:mock-url");
  vi.spyOn(URL, "revokeObjectURL").mockReturnValue(undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("CanvasToolbar", () => {
  it("adds an agent node when + Agent is clicked", async () => {
    const user = userEvent.setup();
    render(<CanvasToolbar />);

    await user.click(screen.getByTestId("add-agent-button"));

    const { nodes } = useCanvasStore.getState();
    expect(nodes).toHaveLength(1);
    expect(nodes[0].type).toBe("agent");
  });

  it("names agent nodes sequentially", async () => {
    const user = userEvent.setup();
    render(<CanvasToolbar />);

    await user.click(screen.getByTestId("add-agent-button"));
    await user.click(screen.getByTestId("add-agent-button"));

    const { nodes } = useCanvasStore.getState();
    const agentNodes = nodes.filter((n) => n.type === "agent");
    expect(agentNodes[0].data.name).toBe("Agent 1");
    expect(agentNodes[1].data.name).toBe("Agent 2");
  });

  it("adds a tool node when + Tool is clicked", async () => {
    const user = userEvent.setup();
    render(<CanvasToolbar />);

    await user.click(screen.getByTestId("add-tool-button"));

    const { nodes } = useCanvasStore.getState();
    expect(nodes).toHaveLength(1);
    expect(nodes[0].type).toBe("tool");
    expect(nodes[0].data.name).toBe("Tool 1");
  });

  it("clears all nodes and edges when Clear is clicked", async () => {
    const user = userEvent.setup();
    // Pre-populate the canvas
    useCanvasStore.getState().setNodes([
      {
        id: "n1",
        type: "agent",
        position: { x: 0, y: 0 },
        data: { id: "n1", name: "A", role: "", instructions: "", modelName: "m", agentType: "worker" },
      },
    ]);
    useCanvasStore.getState().setEdges([
      { id: "e1", source: "n1", target: "n2" },
    ]);
    render(<CanvasToolbar />);

    await user.click(screen.getByTestId("clear-canvas-button"));

    expect(useCanvasStore.getState().nodes).toHaveLength(0);
    expect(useCanvasStore.getState().edges).toHaveLength(0);
  });

  it("updates canvas name when input changes", async () => {
    const user = userEvent.setup();
    render(<CanvasToolbar />);

    const input = screen.getByTestId("canvas-name-input");
    await user.clear(input);
    await user.type(input, "New Name");

    expect(useCanvasStore.getState().canvasName).toBe("New Name");
  });

  it("calls URL.createObjectURL when Export is clicked", async () => {
    const user = userEvent.setup();
    // Spy on anchor click to prevent jsdom navigation errors
    const clickSpy = vi.fn();
    const origCreate = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      const el = origCreate(tag);
      if (tag === "a") {
        vi.spyOn(el as HTMLAnchorElement, "click").mockImplementation(clickSpy);
      }
      return el;
    });

    render(<CanvasToolbar />);
    await user.click(screen.getByTestId("export-button"));

    expect(URL.createObjectURL).toHaveBeenCalledOnce();
    expect(URL.createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    vi.restoreAllMocks();
  });

  it("imports a canvas from a JSON file and updates the store", async () => {
    const { importCanvas } = await import("@/lib/api");
    render(<CanvasToolbar />);

    const payload: CanvasSavePayload = {
      name: "Imported Canvas",
      nodes: { agents: [], tools: [] },
      edges: [],
    };
    const file = new File([JSON.stringify(payload)], "canvas.json", {
      type: "application/json",
    });

    const input = document.querySelector(
      'input[type="file"]'
    ) as HTMLInputElement;
    await userEvent.upload(input, file);

    await waitFor(() => {
      expect(importCanvas).toHaveBeenCalledOnce();
    });

    expect(useCanvasStore.getState().canvasId).toBe("imported-1");
  });

  it("logs an error without crashing when import fails", async () => {
    const { importCanvas } = await import("@/lib/api");
    vi.mocked(importCanvas).mockRejectedValueOnce(new Error("Server error"));
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    render(<CanvasToolbar />);

    const file = new File(["invalid json"], "bad.json", {
      type: "application/json",
    });
    const input = document.querySelector(
      'input[type="file"]'
    ) as HTMLInputElement;
    await userEvent.upload(input, file);

    await waitFor(() => {
      expect(consoleSpy).toHaveBeenCalled();
    });
    consoleSpy.mockRestore();
  });
});
