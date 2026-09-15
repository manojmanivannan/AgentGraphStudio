import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { EdgeProps } from "@xyflow/react";
import { CustomEdge } from "./CustomEdge";

let lastBaseEdgeStyle: React.CSSProperties | undefined;

vi.mock("@xyflow/react", async () => {
  const actual = await vi.importActual<typeof import("@xyflow/react")>("@xyflow/react");
  return {
    ...actual,
    getBezierPath: () => ["M0,0 L10,10", 5, 5],
    useReactFlow: () => ({ deleteElements: vi.fn() }),
    BaseEdge: (props: { style?: React.CSSProperties }) => {
      lastBaseEdgeStyle = props.style;
      return <div data-testid="base-edge" />;
    },
    EdgeLabelRenderer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  };
});

const makeProps = (edgeType?: string): EdgeProps =>
  ({
    id: "edge-1",
    sourceX: 0,
    sourceY: 0,
    targetX: 100,
    targetY: 100,
    sourcePosition: "bottom",
    targetPosition: "top",
    data: edgeType ? { edgeType } : undefined,
    markerEnd: undefined,
  }) as unknown as EdgeProps;

describe("CustomEdge", () => {
  it("renders a dashed agent-colored stroke for handoff edges", () => {
    render(<CustomEdge {...makeProps("handoff")} />);
    expect(screen.getByTestId("base-edge")).toBeInTheDocument();
    expect(lastBaseEdgeStyle?.strokeDasharray).toBe("6 4");
    expect(lastBaseEdgeStyle?.stroke).toBe("var(--color-agent)");
    expect(lastBaseEdgeStyle?.opacity).toBe(0.7);
  });

  it("renders a muted solid stroke for tool_access edges", () => {
    render(<CustomEdge {...makeProps("tool_access")} />);
    expect(lastBaseEdgeStyle?.strokeDasharray).toBeUndefined();
    expect(lastBaseEdgeStyle?.stroke).toBe("var(--color-text-tertiary)");
    expect(lastBaseEdgeStyle?.opacity).toBe(0.4);
  });

  it("renders a solid green stroke for produces edges", () => {
    render(<CustomEdge {...makeProps("produces")} />);
    expect(lastBaseEdgeStyle?.strokeDasharray).toBeUndefined();
    expect(lastBaseEdgeStyle?.stroke).toBe("var(--color-success)");
    expect(lastBaseEdgeStyle?.opacity).toBe(0.6);
  });

  it("renders a solid green stroke for consumes edges", () => {
    render(<CustomEdge {...makeProps("consumes")} />);
    expect(lastBaseEdgeStyle?.strokeDasharray).toBeUndefined();
    expect(lastBaseEdgeStyle?.stroke).toBe("var(--color-success)");
    expect(lastBaseEdgeStyle?.opacity).toBe(0.6);
  });

  it("still renders the hover delete button for produces/consumes edges", () => {
    render(<CustomEdge {...makeProps("produces")} />);
    expect(screen.getByTitle("Delete edge")).toBeInTheDocument();
  });
});
