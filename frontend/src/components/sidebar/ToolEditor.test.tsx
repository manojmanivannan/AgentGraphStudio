import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
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

// Mock the API module
vi.mock("@/lib/api", () => ({
  inspectTool: vi.fn(),
  testTool: vi.fn(),
}));

import { inspectTool, testTool } from "@/lib/api";

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
  vi.clearAllMocks();
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

  it("shows the Test button when a tool node is selected", () => {
    useCanvasStore.getState().setNodes([toolNode]);
    useCanvasStore.getState().selectNode("tool-1");
    render(<ToolEditor />);

    expect(screen.getByTestId("tool-test-button")).toBeInTheDocument();
  });

  it("calls inspectTool when Test button is clicked", async () => {
    const mockInspectResult = {
      function_name: "search",
      arguments: [{ name: "q", type_hint: "str", default_value: null }],
    };
    vi.mocked(inspectTool).mockResolvedValue(mockInspectResult);

    useCanvasStore.getState().setNodes([toolNode]);
    useCanvasStore.getState().selectNode("tool-1");
    render(<ToolEditor />);

    const testButton = screen.getByTestId("tool-test-button");
    await userEvent.setup().click(testButton);

    await waitFor(() => {
      expect(inspectTool).toHaveBeenCalledWith("def search(q):\n    return q", []);
    });
  });

  it("shows argument input fields after successful inspect", async () => {
    const mockInspectResult = {
      function_name: "add",
      arguments: [
        { name: "a", type_hint: "int", default_value: null },
        { name: "b", type_hint: "int", default_value: null },
      ],
    };
    vi.mocked(inspectTool).mockResolvedValue(mockInspectResult);

    useCanvasStore.getState().setNodes([toolNode]);
    useCanvasStore.getState().selectNode("tool-1");
    render(<ToolEditor />);

    const testButton = screen.getByTestId("tool-test-button");
    await userEvent.setup().click(testButton);

    await waitFor(() => {
      expect(screen.getByTestId("tool-test-arg-a")).toBeInTheDocument();
      expect(screen.getByTestId("tool-test-arg-b")).toBeInTheDocument();
    });
  });

  it("shows Run Test button after successful inspect", async () => {
    const mockInspectResult = {
      function_name: "search",
      arguments: [{ name: "q", type_hint: "str", default_value: null }],
    };
    vi.mocked(inspectTool).mockResolvedValue(mockInspectResult);

    useCanvasStore.getState().setNodes([toolNode]);
    useCanvasStore.getState().selectNode("tool-1");
    render(<ToolEditor />);

    await userEvent.setup().click(screen.getByTestId("tool-test-button"));

    await waitFor(() => {
      expect(screen.getByTestId("tool-test-run-button")).toBeInTheDocument();
    });
  });

  it("displays test result on successful run", async () => {
    const mockInspectResult = {
      function_name: "search",
      arguments: [{ name: "q", type_hint: "str", default_value: null }],
    };
    vi.mocked(inspectTool).mockResolvedValue(mockInspectResult);

    const mockTestResult = {
      success: true,
      output: "Hello world",
      execution_time_ms: 15.5,
    };
    vi.mocked(testTool).mockResolvedValue(mockTestResult);

    useCanvasStore.getState().setNodes([toolNode]);
    useCanvasStore.getState().selectNode("tool-1");
    render(<ToolEditor />);

    const user = userEvent.setup();

    // Click "Inspect & Test"
    await user.click(screen.getByTestId("tool-test-button"));

    // Wait for inspect to complete
    await waitFor(() => {
      expect(screen.getByTestId("tool-test-arg-q")).toBeInTheDocument();
    });

    // Fill in the argument
    await user.type(screen.getByTestId("tool-test-arg-q"), "hello");

    // Click "Run Test"
    await user.click(screen.getByTestId("tool-test-run-button"));

    // Wait for result
    await waitFor(() => {
      expect(screen.getByTestId("tool-test-result")).toBeInTheDocument();
    });

    expect(screen.getByTestId("tool-test-result")).toHaveTextContent("Hello world");
  });

  it("displays error result on failed run", async () => {
    const mockInspectResult = {
      function_name: "boom",
      arguments: [],
    };
    vi.mocked(inspectTool).mockResolvedValue(mockInspectResult);

    const mockTestResult = {
      success: false,
      output: "ValueError: kaboom",
      execution_time_ms: 5.2,
    };
    vi.mocked(testTool).mockResolvedValue(mockTestResult);

    useCanvasStore.getState().setNodes([toolNode]);
    useCanvasStore.getState().selectNode("tool-1");
    render(<ToolEditor />);

    const user = userEvent.setup();

    await user.click(screen.getByTestId("tool-test-button"));

    await waitFor(() => {
      expect(screen.getByTestId("tool-test-run-button")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("tool-test-run-button"));

    await waitFor(() => {
      expect(screen.getByTestId("tool-test-result")).toBeInTheDocument();
    });

    expect(screen.getByTestId("tool-test-result")).toHaveTextContent("kaboom");
  });

  it("shows error message when inspectTool fails", async () => {
    vi.mocked(inspectTool).mockRejectedValue(new Error("Syntax error in tool"));

    useCanvasStore.getState().setNodes([toolNode]);
    useCanvasStore.getState().selectNode("tool-1");
    render(<ToolEditor />);

    await userEvent.setup().click(screen.getByTestId("tool-test-button"));

    await waitFor(() => {
      expect(screen.getByTestId("tool-test-error")).toBeInTheDocument();
    });
  });
});