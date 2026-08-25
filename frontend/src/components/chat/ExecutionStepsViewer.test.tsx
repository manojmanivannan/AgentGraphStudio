import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ExecutionStepsViewer } from "./ExecutionStepsViewer";
import type { Message } from "@/types";

describe("ExecutionStepsViewer", () => {
  const defaultProps = {
    steps: [],
    isStreaming: false,
    isExpanded: true,
    collapsedSteps: new Set<string>(),
    toggleStepExpand: vi.fn(),
    getMessageNestingLevel: () => 0,
    activeInterrupt: null,
    handleSendHumanResponse: vi.fn(),
    handleSendToolApproval: vi.fn(),
    inlineInputRef: { current: null },
    renderMessageContent: (content: string) => <div>{content}</div>,
  };

  it("renders python code block and output for coding tool executions", async () => {
    const pythonCode = "import numpy as np\nprint(np.mean([1, 2, 3]))";
    const codingStep: Message = {
      id: "step-1",
      conversation_id: "conv-1",
      role: "tool",
      content: "2.0\n",
      agent_name: "CoderAgent",
      tool: "run_code",
      event_type: "tool_result",
      args: { python_code: pythonCode },
      created_at: "2026-01-01T00:00:00.000Z",
    };

    render(<ExecutionStepsViewer {...defaultProps} steps={[codingStep]} />);

    // Step header with agent name and tool
    expect(screen.getByText(/CoderAgent · run_code/i)).toBeInTheDocument();

    // Python code section
    expect(screen.getByText("Python Code")).toBeInTheDocument();
    expect(screen.getByText((content) => content.includes("import numpy as np"))).toBeInTheDocument();

    // Output section
    expect(screen.getByText("Output")).toBeInTheDocument();
    expect(screen.getByText("2.0")).toBeInTheDocument();
  });

  it("allows copying python code to clipboard", async () => {
    const pythonCode = "print('hello world')";
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    const codingStep: Message = {
      id: "step-1",
      conversation_id: "conv-1",
      role: "tool",
      content: "hello world\n",
      agent_name: "CoderAgent",
      tool: "run_code",
      event_type: "tool_result",
      args: { python_code: pythonCode },
      created_at: "2026-01-01T00:00:00.000Z",
    };

    render(<ExecutionStepsViewer {...defaultProps} steps={[codingStep]} />);

    const copyBtn = screen.getByTitle("Copy code");
    fireEvent.click(copyBtn);

    expect(writeTextMock).toHaveBeenCalledWith(pythonCode);
    expect(screen.getByText("Copied")).toBeInTheDocument();
  });

  it("renders pip install command for pip_install tool executions", () => {
    const pipStep: Message = {
      id: "step-pip",
      conversation_id: "conv-1",
      role: "tool",
      content: "Successfully installed scipy-1.11.0\n",
      agent_name: "WorkerAgent",
      tool: "pip_install",
      event_type: "tool_result",
      args: { packages: ["scipy", "seaborn"] },
      created_at: "2026-01-01T00:00:00.000Z",
    };

    render(<ExecutionStepsViewer {...defaultProps} steps={[pipStep]} />);

    expect(screen.getByText(/WorkerAgent · pip_install/i)).toBeInTheDocument();
    expect(screen.getByText("pip install scipy seaborn")).toBeInTheDocument();
    expect(screen.getByText("Successfully installed scipy-1.11.0")).toBeInTheDocument();
  });

  it("renders general tool arguments when present", () => {
    const customToolStep: Message = {
      id: "step-custom",
      conversation_id: "conv-1",
      role: "tool",
      content: "Found 5 records",
      agent_name: "SearchAgent",
      tool: "search_db",
      event_type: "tool_result",
      args: { query: "sales 2026", limit: 5 },
      created_at: "2026-01-01T00:00:00.000Z",
    };

    render(<ExecutionStepsViewer {...defaultProps} steps={[customToolStep]} />);

    expect(screen.getByText(/SearchAgent · search_db/i)).toBeInTheDocument();
    expect(screen.getByText("Arguments")).toBeInTheDocument();
    expect(screen.getByText(/sales 2026/)).toBeInTheDocument();
    expect(screen.getByText("Found 5 records")).toBeInTheDocument();
  });

  it("falls back to plain content rendering when no structured args provided", () => {
    const simpleStep: Message = {
      id: "step-simple",
      conversation_id: "conv-1",
      role: "tool",
      content: "Simple tool output",
      agent_name: "SimpleAgent",
      event_type: "tool_result",
      created_at: "2026-01-01T00:00:00.000Z",
    };

    render(<ExecutionStepsViewer {...defaultProps} steps={[simpleStep]} />);

    expect(screen.getByText(/SimpleAgent · tool_result/i)).toBeInTheDocument();
    expect(screen.getByText("Simple tool output")).toBeInTheDocument();
    expect(screen.queryByText("Python Code")).not.toBeInTheDocument();
  });
});
