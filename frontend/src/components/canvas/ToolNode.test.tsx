import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ReactFlowProvider } from "@xyflow/react";
import { useCanvasStore } from "@/store/canvasStore";
import { ToolNode } from "./ToolNode";
import type { ToolNodeData } from "@/types";

vi.mock("@xyflow/react", async () => {
  const actual = await vi.importActual<typeof import("@xyflow/react")>("@xyflow/react");
  return {
    ...actual,
    Handle: () => null,
  };
});

const makeProps = (data: Partial<ToolNodeData> = {}): any => ({
  id: data.id ?? "tool-1",
  type: "tool" as const,
  selected: false,
  zIndex: 0,
  isConnectable: true,
  xPos: 0,
  yPos: 0,
  dragging: false,
  data: {
    ...data,
    id: data.id ?? "tool-1",
    name: data.name ?? "My Tool",
    code: data.code ?? "",
  } as any,
});

beforeEach(() => {
  useCanvasStore.getState().reset();
});

describe("ToolNode", () => {
  it("renders the tool name", () => {
    render(<ToolNode {...makeProps({ name: "Calculator" })} />);
    expect(screen.getByText("Calculator")).toBeInTheDocument();
  });

  it("shows first 3 lines of code as preview", () => {
    const code = "def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b";
    render(<ToolNode {...makeProps({ code })} />);
    expect(screen.getByText(/def add\(a, b\)/)).toBeInTheDocument();
    expect(screen.queryByText(/def subtract/)).not.toBeInTheDocument();
  });

  it("shows placeholder when code is empty", () => {
    render(<ToolNode {...makeProps({ code: "" })} />);
    expect(screen.getByText("Write Python code")).toBeInTheDocument();
  });

  it("applies active pulse style when node is the active execution node", () => {
    useCanvasStore.getState().setActiveNodeId("tool-1");
    const { container } = render(<ToolNode {...makeProps({ id: "tool-1" })} />);
    expect(container.firstChild).toHaveClass("glow-active-pulse");
  });

  it("does not apply active pulse when node is not the active execution node", () => {
    useCanvasStore.getState().setActiveNodeId("other-node");
    const { container } = render(<ToolNode {...makeProps({ id: "tool-1" })} />);
    expect(container.firstChild).not.toHaveClass("glow-active-pulse");
  });

  it("renders resize handles so the node can be resized like agent/router nodes", () => {
    const { container } = render(
      <ReactFlowProvider>
        <ToolNode {...makeProps({ id: "tool-1" })} selected />
      </ReactFlowProvider>
    );
    expect(container.querySelectorAll(".react-flow__resize-control").length).toBeGreaterThan(0);
  });

  it("gives the Settings gear button a p-1.5 hit target instead of p-1", () => {
    render(<ToolNode {...makeProps()} />);
    const settingsButton = screen.getByTitle("Settings");
    expect(settingsButton).toHaveClass("p-1.5");
    expect(settingsButton).not.toHaveClass("p-1");
  });

  it("uses the info glow variable for the selected shadow", () => {
    const { container } = render(
      <ReactFlowProvider>
        <ToolNode {...makeProps({ id: "tool-1" })} selected />
      </ReactFlowProvider>
    );
    expect(container.firstChild).toHaveClass(/var\(--color-info-glow\)/);
    expect(container.firstChild).not.toHaveClass(/rgba\(59,130,246/);
  });

  // --- MCP grant indication (#136): resolved vs not-yet-granting imports ---

  it("shows the granted-tool count for a resolved MCP-backed node", () => {
    render(
      <ToolNode
        {...makeProps({
          code: "",
          mcpServerId: "srv-1",
          mcpTools: [
            { name: "web_search", requiresApproval: true },
            { name: "read_doc", requiresApproval: false },
          ],
        })}
      />
    );
    const indicator = screen.getByTestId("mcp-grant-indicator");
    expect(indicator).toHaveTextContent(/2/);
    expect(screen.queryByTestId("mcp-unresolved-indicator")).not.toBeInTheDocument();
  });

  it("shows an unresolved indication for a not-yet-granting MCP import", () => {
    render(
      <ToolNode
        {...makeProps({
          code: "",
          mcpServerId: null,
          mcpTools: [{ name: "web_search", requiresApproval: false }],
        })}
      />
    );
    expect(screen.getByTestId("mcp-unresolved-indicator")).toBeInTheDocument();
    expect(screen.getByTestId("mcp-unresolved-indicator")).toHaveTextContent(
      /MCP server unresolved/i
    );
    expect(screen.queryByTestId("mcp-grant-indicator")).not.toBeInTheDocument();
  });

  it("shows neither MCP indication for a plain code tool", () => {
    render(<ToolNode {...makeProps({ code: "def add(): ..." })} />);
    expect(screen.queryByTestId("mcp-grant-indicator")).not.toBeInTheDocument();
    expect(screen.queryByTestId("mcp-unresolved-indicator")).not.toBeInTheDocument();
  });
});
