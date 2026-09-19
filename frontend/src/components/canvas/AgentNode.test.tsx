import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { useCanvasStore } from "@/store/canvasStore";
import { AgentNode } from "./AgentNode";
import type { AgentNodeData } from "@/types";

// Handle requires ReactFlow's internal context — replace with a plain div in unit
// tests so we can still assert on the accessibility props passed through to it.
vi.mock("@xyflow/react", async () => {
  const actual = await vi.importActual<typeof import("@xyflow/react")>("@xyflow/react");
  return {
    ...actual,
    Handle: ({ id, title, "aria-label": ariaLabel }: any) => (
      <div data-testid={`handle-${id}`} title={title} aria-label={ariaLabel} />
    ),
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

  it("gives every connection handle a matching title and aria-label", () => {
    render(<AgentNode {...makeProps()} />);
    const expected: Record<string, string> = {
      "handle-agent-in": "Agent handoff input",
      "handle-agent-out": "Agent handoff output",
      "handle-tool-out": "Tool access",
      "handle-attachment-in": "Attachment input (consumes)",
      "handle-attachment-out": "Attachment output (produces)",
    };
    for (const [testId, label] of Object.entries(expected)) {
      const handle = screen.getByTestId(testId);
      expect(handle).toHaveAttribute("title", label);
      expect(handle).toHaveAttribute("aria-label", label);
    }
  });
});
