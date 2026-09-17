import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ReactFlowProvider } from "@xyflow/react";
import { useCanvasStore } from "@/store/canvasStore";
import { AttachmentNode } from "./AttachmentNode";
import type { AttachmentNodeData } from "@/types";

vi.mock("@xyflow/react", async () => {
  const actual = await vi.importActual<typeof import("@xyflow/react")>("@xyflow/react");
  return {
    ...actual,
    Handle: () => null,
  };
});

const makeProps = (data: Partial<AttachmentNodeData> = {}): any => ({
  id: data.id ?? "att-1",
  type: "attachment" as const,
  selected: false,
  zIndex: 0,
  isConnectable: true,
  xPos: 0,
  yPos: 0,
  dragging: false,
  data: {
    id: data.id ?? "att-1",
    name: data.name ?? "My Attachment",
    fileType: data.fileType ?? "text",
    description: data.description ?? "",
  } as any,
});

beforeEach(() => {
  useCanvasStore.getState().reset();
});

describe("AttachmentNode", () => {
  it("renders the attachment name", () => {
    render(<AttachmentNode {...makeProps({ name: "Sales Data" })} />);
    expect(screen.getByText("Sales Data")).toBeInTheDocument();
  });

  it("shows the file_type value as the header badge", () => {
    render(<AttachmentNode {...makeProps({ fileType: "csv" })} />);
    expect(screen.getByText("CSV")).toBeInTheDocument();
  });

  it("shows a different file_type badge", () => {
    render(<AttachmentNode {...makeProps({ fileType: "python" })} />);
    expect(screen.getByText("PYTHON")).toBeInTheDocument();
  });

  it("renders description text when provided", () => {
    render(<AttachmentNode {...makeProps({ description: "Q1 sales export" })} />);
    expect(screen.getByText("Q1 sales export")).toBeInTheDocument();
  });

  it("shows placeholder when description is empty", () => {
    render(<AttachmentNode {...makeProps({ description: "" })} />);
    expect(screen.getByText("No description")).toBeInTheDocument();
  });

  it("applies active pulse style when node is the active execution node", () => {
    useCanvasStore.getState().setActiveNodeId("att-1");
    const { container } = render(<AttachmentNode {...makeProps({ id: "att-1" })} />);
    expect(container.firstChild).toHaveClass("glow-active-pulse");
  });

  it("does not apply active pulse when node is not the active execution node", () => {
    useCanvasStore.getState().setActiveNodeId("other-node");
    const { container } = render(<AttachmentNode {...makeProps({ id: "att-1" })} />);
    expect(container.firstChild).not.toHaveClass("glow-active-pulse");
  });

  it("renders resize handles so the node can be resized like agent/router nodes", () => {
    const { container } = render(
      <ReactFlowProvider>
        <AttachmentNode {...makeProps({ id: "att-1" })} selected />
      </ReactFlowProvider>
    );
    expect(container.querySelectorAll(".react-flow__resize-control").length).toBeGreaterThan(0);
  });
});
