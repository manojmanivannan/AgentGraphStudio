import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ReactFlowProvider } from "@xyflow/react";
import { useCanvasStore } from "@/store/canvasStore";
import { ToolNode } from "./ToolNode";
import type { McpToolGrantData, ToolNodeData } from "@/types";

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
    id: data.id ?? "tool-1",
    name: data.name ?? "My Tool",
    code: data.code ?? "",
    ...data,
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
});

const grant = (name: string, vanished = false): McpToolGrantData => ({
  name,
  requiresApproval: false,
  ...(vanished ? { vanished } : {}),
});

describe("ToolNode MCP variant", () => {
  const makeMcpProps = (data: Partial<ToolNodeData> = {}): any =>
    makeProps({
      code: "",
      mcpServerId: "server-1",
      mcpServerName: "Weather Station",
      mcpTools: [],
      ...data,
    });

  it("renders in the agent-purple family, distinct from the code-tool info family", () => {
    const { container } = render(<ToolNode {...makeMcpProps()} />);
    expect(container.querySelector("[data-testid='tool-node-header']")).toHaveClass(
      /var\(--color-agent-surface\)/
    );
    expect(container.querySelector("[data-testid='tool-node-header']")).not.toHaveClass(
      /var\(--color-info-surface\)/
    );
  });

  it("keeps the purple family when selected", () => {
    const { container } = render(
      <ReactFlowProvider>
        <ToolNode {...makeMcpProps()} selected={true as any} />
      </ReactFlowProvider>
    );
    expect(container.querySelector("[data-testid='tool-node']")).toHaveClass(
      /var\(--color-agent-glow\)/
    );
    expect(container.querySelector("[data-testid='tool-node']")).not.toHaveClass(
      /var\(--color-info-glow\)/
    );
  });

  it("renders the server name with a server icon", () => {
    render(<ToolNode {...makeMcpProps()} />);
    expect(screen.getByTestId("mcp-server-name")).toHaveTextContent("Weather Station");
    expect(screen.getByTestId("mcp-server-icon")).toBeInTheDocument();
  });

  it("falls back to the server id when no server name is in node data", () => {
    render(<ToolNode {...makeMcpProps({ mcpServerName: undefined })} />);
    expect(screen.getByTestId("mcp-server-name")).toHaveTextContent("server-1");
  });

  it("shows an N-tools badge equal to the enabled-tools count", () => {
    render(
      <ToolNode
        {...makeMcpProps({
          mcpTools: [grant("get_forecast"), grant("get_humidity"), grant("convert_units")],
        })}
      />
    );
    expect(screen.getByTestId("mcp-tools-badge")).toHaveTextContent("3 tools");
  });

  it("renders a chip for every enabled tool", () => {
    render(
      <ToolNode
        {...makeMcpProps({ mcpTools: [grant("get_forecast"), grant("get_humidity")] })}
      />
    );
    const chips = screen.getAllByTestId("mcp-tool-chip");
    expect(chips).toHaveLength(2);
    expect(chips[0]).toHaveTextContent("get_forecast");
    expect(chips[1]).toHaveTextContent("get_humidity");
  });

  it("renders an enabled-but-vanished tool chip struck-through", () => {
    render(
      <ToolNode
        {...makeMcpProps({
          mcpTools: [grant("get_forecast"), grant("get_humidity", true)],
        })}
      />
    );
    const chips = screen.getAllByTestId("mcp-tool-chip");
    expect(chips).toHaveLength(2);
    expect(chips[0]).not.toHaveClass("line-through");
    expect(chips[1]).toHaveClass("line-through");
    expect(chips[1]).toHaveTextContent("get_humidity");
  });

  it("shows no code preview for MCP-backed nodes even if stale code is present", () => {
    render(
      <ToolNode
        {...makeMcpProps({ code: "def legacy_tool():\n    pass", mcpTools: [grant("get_forecast")] })}
      />
    );
    expect(screen.queryByText(/def legacy_tool/)).not.toBeInTheDocument();
    expect(screen.queryByText("Write Python code")).not.toBeInTheDocument();
  });

  it("keeps the code-tool rendering unchanged (info family + code preview)", () => {
    const { container } = render(
      <ToolNode
        {...makeProps({
          code: "def add(a, b):\n    return a + b",
          mcpServerId: null,
          mcpTools: [],
          name: "Calculator",
        })}
      />
    );
    expect(container.querySelector("[data-testid='tool-node-header']")).toHaveClass(
      /var\(--color-info-surface\)/
    );
    expect(screen.getByText(/def add\(a, b\)/)).toBeInTheDocument();
    expect(screen.queryByTestId("mcp-server-name")).not.toBeInTheDocument();
    expect(screen.queryByTestId("mcp-tools-badge")).not.toBeInTheDocument();
    expect(screen.queryByTestId("mcp-tool-chip")).not.toBeInTheDocument();
  });
});
