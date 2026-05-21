import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
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

const makeProps = (data: Partial<ToolNodeData> = {}) => ({
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
    expect(container.firstChild).toHaveClass("animate-pulse");
  });

  it("does not apply active pulse when node is not the active execution node", () => {
    useCanvasStore.getState().setActiveNodeId("other-node");
    const { container } = render(<ToolNode {...makeProps({ id: "tool-1" })} />);
    expect(container.firstChild).not.toHaveClass("animate-pulse");
  });
});
