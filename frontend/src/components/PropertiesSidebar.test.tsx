import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useCanvasStore } from "@/store/canvasStore";
import { PropertiesSidebar } from "./PropertiesSidebar";
import type { Node } from "@xyflow/react";

// Mock Monaco so ToolEditor renders without WebGL
vi.mock("@monaco-editor/react", () => ({
  default: ({ value, onChange }: { value?: string; onChange?: (v: string) => void }) => (
    <textarea
      data-testid="tool-code-editor"
      value={value ?? ""}
      onChange={(e) => onChange?.(e.target.value)}
    />
  ),
}));

const agentNode: Node = {
  id: "agent-1",
  type: "agent",
  position: { x: 0, y: 0 },
  data: {
    id: "agent-1",
    name: "My Agent",
    role: "Does things",
    instructions: "",
    modelName: "ollama:llama3.1",
    agentType: "worker",
  },
};

const toolNode: Node = {
  id: "tool-1",
  type: "tool",
  position: { x: 0, y: 0 },
  data: { id: "tool-1", name: "My Tool", code: "" },
};

beforeEach(() => {
  useCanvasStore.getState().reset();
});

describe("PropertiesSidebar", () => {
  it("is collapsed by default and shows only the toggle button", () => {
    render(<PropertiesSidebar />);
    expect(screen.getByTestId("properties-toggle")).toBeInTheDocument();
    // No close button when collapsed
    expect(screen.queryByTestId("properties-close")).not.toBeInTheDocument();
  });

  it("expands the panel when the toggle button is clicked", async () => {
    const user = userEvent.setup();
    render(<PropertiesSidebar />);

    await user.click(screen.getByTestId("properties-toggle"));

    expect(screen.getByTestId("properties-close")).toBeInTheDocument();
  });

  it("renders AgentEditor when an agent node is selected", () => {
    useCanvasStore.getState().setNodes([agentNode]);
    useCanvasStore.getState().selectNode("agent-1"); // also opens panel
    render(<PropertiesSidebar />);

    expect(screen.getByTestId("agent-name-input")).toBeInTheDocument();
  });

  it("renders ToolEditor when a tool node is selected", () => {
    useCanvasStore.getState().setNodes([toolNode]);
    useCanvasStore.getState().selectNode("tool-1");
    render(<PropertiesSidebar />);

    expect(screen.getByTestId("tool-name-input")).toBeInTheDocument();
  });

  it("shows placeholder when panel is open but no node is selected", async () => {
    const user = userEvent.setup();
    render(<PropertiesSidebar />);

    await user.click(screen.getByTestId("properties-toggle"));

    expect(
      screen.getByText("Select a node to edit its properties")
    ).toBeInTheDocument();
  });

  it("closes the panel and deselects the node when X is clicked", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setNodes([agentNode]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<PropertiesSidebar />);

    await user.click(screen.getByTestId("properties-close"));

    expect(useCanvasStore.getState().selectedNodeId).toBeNull();
    expect(useCanvasStore.getState().propertiesOpen).toBe(false);
  });

  it("shows the blue indicator dot when a node is selected and panel is collapsed", () => {
    useCanvasStore.getState().setNodes([agentNode]);
    // Set selected node without opening panel
    useCanvasStore.getState().setNodes([agentNode]);
    // Manually set selectedNodeId without opening via selectNode (which opens panel)
    useCanvasStore.setState({ selectedNodeId: "agent-1", propertiesOpen: false });

    render(<PropertiesSidebar />);

    // The indicator dot is shown
    expect(screen.getByTitle("Node selected")).toBeInTheDocument();
  });
});
