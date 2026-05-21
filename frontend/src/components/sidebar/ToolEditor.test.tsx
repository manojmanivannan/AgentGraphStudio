import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useCanvasStore } from "@/store/canvasStore";
import { ToolEditor } from "./ToolEditor";
import type { Node } from "@xyflow/react";

// Mock Monaco so it renders as a textarea
vi.mock("@monaco-editor/react", () => ({
  default: ({
    value,
    onChange,
  }: {
    value?: string;
    onChange?: (v: string | undefined) => void;
  }) => (
    <textarea
      data-testid="tool-code-editor"
      value={value ?? ""}
      onChange={(e) => onChange?.(e.target.value)}
    />
  ),
}));

const toolNode: Node = {
  id: "tool-1",
  type: "tool",
  position: { x: 0, y: 0 },
  data: {
    id: "tool-1",
    name: "WebSearch",
    code: "def search(q):\n    return q",
  },
};

beforeEach(() => {
  useCanvasStore.getState().reset();
});

describe("ToolEditor", () => {
  it("shows placeholder when no tool node is selected", () => {
    render(<ToolEditor />);
    expect(
      screen.getByText("Select a tool node to edit its code")
    ).toBeInTheDocument();
  });

  it("renders name input and code editor for a selected tool node", () => {
    useCanvasStore.getState().setNodes([toolNode]);
    useCanvasStore.getState().selectNode("tool-1");
    render(<ToolEditor />);

    expect(screen.getByTestId("tool-name-input")).toHaveValue("WebSearch");
    expect(screen.getByTestId("tool-code-editor")).toHaveValue(
      "def search(q):\n    return q"
    );
  });

  it("updates the tool name in the store when typed", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setNodes([toolNode]);
    useCanvasStore.getState().selectNode("tool-1");
    render(<ToolEditor />);

    await user.clear(screen.getByTestId("tool-name-input"));
    await user.type(screen.getByTestId("tool-name-input"), "Calculator");

    const stored = useCanvasStore.getState().nodes.find((n) => n.id === "tool-1");
    expect(stored?.data.name).toBe("Calculator");
  });

  it("updates the code in the store when the editor changes", () => {
    useCanvasStore.getState().setNodes([toolNode]);
    useCanvasStore.getState().selectNode("tool-1");
    render(<ToolEditor />);

    fireEvent.change(screen.getByTestId("tool-code-editor"), {
      target: { value: "def new_code(): pass" },
    });

    const stored = useCanvasStore.getState().nodes.find((n) => n.id === "tool-1");
    expect(stored?.data.code).toBe("def new_code(): pass");
  });

  it("shows no placeholder when a tool node is selected", () => {
    useCanvasStore.getState().setNodes([toolNode]);
    useCanvasStore.getState().selectNode("tool-1");
    render(<ToolEditor />);

    expect(
      screen.queryByText("Select a tool node to edit its code")
    ).not.toBeInTheDocument();
  });
});
