import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ReactFlowProvider } from "@xyflow/react";
import { useCanvasStore } from "@/store/canvasStore";
import { AgentNode } from "./AgentNode";
import type { AgentNodeData } from "@/types";

// Handle requires ReactFlow's internal context — replace with a no-op in unit tests
vi.mock("@xyflow/react", async () => {
  const actual = await vi.importActual<typeof import("@xyflow/react")>("@xyflow/react");
  return {
    ...actual,
    Handle: () => null,
  };
});

const makeProps = (data: Partial<AgentNodeData> = {}): any => ({
  id: data.id ?? "node-1",
  type: "agent" as const,
  selected: false,
  zIndex: 0,
  isConnectable: true,
  xPos: 0,
  yPos: 0,
  dragging: false,
  data: {
    id: data.id ?? "node-1",
    name: data.name ?? "My Agent",
    role: data.role ?? "",
    instructions: data.instructions ?? "",
    modelName: data.modelName ?? "ollama:llama3.1",
    agentType: data.agentType ?? "worker",
  } as any,
  ...data,
});

beforeEach(() => {
  useCanvasStore.getState().reset();
});

describe("AgentNode", () => {
  it("renders the agent name", () => {
    render(<AgentNode {...makeProps({ name: "Research Bot" })} />);
    expect(screen.getByText("Research Bot")).toBeInTheDocument();
  });

  it("shows Worker badge for worker agent type", () => {
    render(<AgentNode {...makeProps({ agentType: "worker" })} />);
    expect(screen.getByText("Worker")).toBeInTheDocument();
  });

  it("shows Router badge for router agent type", () => {
    render(<AgentNode {...makeProps({ agentType: "router" })} />);
    expect(screen.getByText("Router")).toBeInTheDocument();
  });

  it("renders role text when provided", () => {
    render(<AgentNode {...makeProps({ role: "Handles research queries" })} />);
    expect(screen.getByText("Handles research queries")).toBeInTheDocument();
  });

  it("renders instructions text when provided", () => {
    render(<AgentNode {...makeProps({ instructions: "Be concise." })} />);
    expect(screen.getByText("Be concise.")).toBeInTheDocument();
  });

  it("shows placeholder when role and instructions are both empty", () => {
    render(<AgentNode {...makeProps({ role: "", instructions: "" })} />);
    expect(screen.getByText("Configure agent properties")).toBeInTheDocument();
  });

  it("applies active pulse style when node is the active execution node", () => {
    useCanvasStore.getState().setActiveNodeId("node-1");
    const { container } = render(<AgentNode {...makeProps({ id: "node-1" })} />);
    expect(container.firstChild).toHaveClass("glow-active-pulse");
  });

  it("does not apply active pulse when node is not the active execution node", () => {
    useCanvasStore.getState().setActiveNodeId("other-node");
    const { container } = render(<AgentNode {...makeProps({ id: "node-1" })} />);
    expect(container.firstChild).not.toHaveClass("glow-active-pulse");
  });

  it("gives the Settings gear button a p-1.5 hit target instead of p-1", () => {
    render(<AgentNode {...makeProps()} />);
    const settingsButton = screen.getByTitle("Settings");
    expect(settingsButton).toHaveClass("p-1.5");
    expect(settingsButton).not.toHaveClass("p-1");
  });

  it("uses the worker accent color for the selected border", () => {
    const { container } = render(
      <ReactFlowProvider>
        <AgentNode {...makeProps({ agentType: "worker" })} selected />
      </ReactFlowProvider>
    );
    expect(container.firstChild).toHaveClass("border-[var(--color-accent)]");
    expect(container.firstChild).not.toHaveClass("border-[var(--color-agent)]");
  });

  it("uses the router color for the selected border instead of the worker accent", () => {
    const { container } = render(
      <ReactFlowProvider>
        <AgentNode {...makeProps({ agentType: "router" })} selected />
      </ReactFlowProvider>
    );
    expect(container.firstChild).toHaveClass("border-[var(--color-agent)]");
    expect(container.firstChild).not.toHaveClass("border-[var(--color-accent)]");
  });
});
