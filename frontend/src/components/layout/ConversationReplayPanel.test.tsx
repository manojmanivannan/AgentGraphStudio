import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useCanvasStore } from "@/store/canvasStore";
import { ConversationReplayPanel } from "./ConversationReplayPanel";

vi.mock("@/lib/api", () => ({
  importConversationZip: vi.fn(),
  listConversations: vi.fn(),
  getConversation: vi.fn(),
}));

describe("ConversationReplayPanel", () => {
  beforeEach(() => {
    useCanvasStore.getState().reset();
    useCanvasStore.getState().setCanvas("canvas-1", "Canvas One");
  });

  it("starts collapsed and expands from a floating launcher", async () => {
    const user = userEvent.setup();

    render(<ConversationReplayPanel />);

    expect(screen.getByTestId("replay-launcher-button")).toBeInTheDocument();
    expect(screen.queryByTestId("conversation-replay-panel")).not.toBeInTheDocument();

    await user.click(screen.getByTestId("replay-launcher-button"));

    expect(screen.getByTestId("conversation-replay-panel")).toBeInTheDocument();
  });

  it("imports a conversation and shows first replay message", async () => {
    const user = userEvent.setup();
    const { importConversationZip } = await import("@/lib/api");

    vi.mocked(importConversationZip).mockResolvedValue({
      id: "conv-1",
      canvas_id: "canvas-1",
      name: "Imported Conversation",
      status: "active",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
      messages: [
        {
          id: "m1",
          conversation_id: "conv-1",
          role: "user",
          content: "Hello there",
          node_id: null,
          created_at: "2026-01-01T00:00:01Z",
        },
        {
          id: "m2",
          conversation_id: "conv-1",
          role: "assistant",
          content: "Hi, I can help",
          node_id: "agent-1",
          created_at: "2026-01-01T00:00:02Z",
        },
      ],
    } as any);

    render(<ConversationReplayPanel />);

  await user.click(screen.getByTestId("replay-launcher-button"));

    const file = new File(["zipcontent"], "conversation.zip", { type: "application/zip" });
    const input = screen.getByTestId("replay-file-input");
    await user.upload(input, file);

    await waitFor(() => {
      expect(screen.getByTestId("replay-current-message")).toHaveTextContent("Hello there");
      expect(screen.getByTestId("replay-step-indicator")).toHaveTextContent("1/2");
      expect(screen.getByTestId("replay-conversation-name")).toHaveTextContent("Imported Conversation");
    });
  });

  it("navigates next and previous, updating highlighted node", async () => {
    const user = userEvent.setup();
    const { importConversationZip } = await import("@/lib/api");

    vi.mocked(importConversationZip).mockResolvedValue({
      id: "conv-1",
      canvas_id: "canvas-1",
      name: "Replay",
      status: "active",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
      messages: [
        {
          id: "m1",
          conversation_id: "conv-1",
          role: "user",
          content: "Question",
          node_id: null,
          created_at: "2026-01-01T00:00:01Z",
        },
        {
          id: "m2",
          conversation_id: "conv-1",
          role: "assistant",
          content: "Answer",
          agent_name: "Research Agent",
          node_id: "agent-1",
          created_at: "2026-01-01T00:00:02Z",
        },
      ],
    } as any);

    render(<ConversationReplayPanel />);

    await user.click(screen.getByTestId("replay-launcher-button"));

    const file = new File(["zipcontent"], "conversation.zip", { type: "application/zip" });
    const input = screen.getByTestId("replay-file-input");
    await user.upload(input, file);

    await waitFor(() => {
      expect(screen.getByTestId("replay-current-message")).toHaveTextContent("Question");
      expect(useCanvasStore.getState().activeNodeId).toBeNull();
    });

    await user.click(screen.getByTestId("replay-next-button"));

    await waitFor(() => {
      expect(screen.getByTestId("replay-current-message")).toHaveTextContent("Answer");
      expect(screen.getByTestId("replay-current-actor")).toHaveTextContent("Research Agent");
      expect(useCanvasStore.getState().activeNodeId).toBe("agent-1");
    });

    await user.click(screen.getByTestId("replay-prev-button"));

    await waitFor(() => {
      expect(screen.getByTestId("replay-current-message")).toHaveTextContent("Question");
      expect(useCanvasStore.getState().activeNodeId).toBeNull();
    });
  });

  it("shows backend error detail for wrong-canvas conversation imports", async () => {
    const user = userEvent.setup();
    const { importConversationZip } = await import("@/lib/api");

    vi.mocked(importConversationZip).mockRejectedValue(
      new Error("This conversation belongs to canvas 'Finance Flow'. Please switch to that canvas before importing.")
    );

    render(<ConversationReplayPanel />);

  await user.click(screen.getByTestId("replay-launcher-button"));

    const file = new File(["zipcontent"], "conversation.zip", { type: "application/zip" });
    const input = screen.getByTestId("replay-file-input");
    await user.upload(input, file);

    await waitFor(() => {
      expect(screen.getByTestId("replay-error")).toHaveTextContent(
        "This conversation belongs to canvas 'Finance Flow'. Please switch to that canvas before importing."
      );
    });
  });

  it("highlights tool node by tool name when replay tool message has no node_id", async () => {
    const user = userEvent.setup();
    const { importConversationZip } = await import("@/lib/api");

    useCanvasStore.getState().setNodes([
      {
        id: "tool-weather-1",
        type: "tool",
        position: { x: 0, y: 0 },
        data: {
          id: "tool-weather-1",
          name: "get_weather_forecast",
          code: "def get_weather_forecast(city: str): return city",
        },
      } as any,
    ]);

    vi.mocked(importConversationZip).mockResolvedValue({
      id: "conv-1",
      canvas_id: "canvas-1",
      name: "Tool Replay",
      status: "active",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
      messages: [
        {
          id: "m1",
          conversation_id: "conv-1",
          role: "tool",
          content: "Execution error in get_weather_forecast: ...",
          agent_name: "get_weather_forecast",
          node_id: null,
          event_type: "tool_result",
          created_at: "2026-01-01T00:00:02Z",
        },
      ],
    } as any);

    render(<ConversationReplayPanel />);

    await user.click(screen.getByTestId("replay-launcher-button"));

    const file = new File(["zipcontent"], "conversation.zip", { type: "application/zip" });
    const input = screen.getByTestId("replay-file-input");
    await user.upload(input, file);

    await waitFor(() => {
      expect(screen.getByTestId("replay-current-message")).toHaveTextContent(
        "Execution error in get_weather_forecast"
      );
      expect(useCanvasStore.getState().activeNodeId).toBe("tool-weather-1");
    });
  });

  it("normalizes persisted assistant tool_result to Tool role and highlights tool node", async () => {
    const user = userEvent.setup();
    const { importConversationZip } = await import("@/lib/api");

    useCanvasStore.getState().setNodes([
      {
        id: "agent-weather-1",
        type: "agent",
        position: { x: 0, y: 0 },
        data: {
          id: "agent-weather-1",
          name: "Weather Agent",
          role: "",
          instructions: "",
          modelName: "ollama:llama3.1",
          agentType: "worker",
        },
      } as any,
      {
        id: "tool-weather-2",
        type: "tool",
        position: { x: 120, y: 0 },
        data: {
          id: "tool-weather-2",
          name: "get_weather_forecast",
          code: "def get_weather_forecast(city: str): return city",
        },
      } as any,
    ]);

    vi.mocked(importConversationZip).mockResolvedValue({
      id: "conv-1",
      canvas_id: "canvas-1",
      name: "Tool Replay Normalized",
      status: "active",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
      messages: [
        {
          id: "m1",
          conversation_id: "conv-1",
          role: "assistant",
          content: "Forecast: sunny",
          agent_name: "get_weather_forecast",
          node_id: "agent-weather-1",
          event_type: "tool_result",
          created_at: "2026-01-01T00:00:02Z",
        },
      ],
    } as any);

    render(<ConversationReplayPanel />);

    await user.click(screen.getByTestId("replay-launcher-button"));

    const file = new File(["zipcontent"], "conversation.zip", { type: "application/zip" });
    const input = screen.getByTestId("replay-file-input");
    await user.upload(input, file);

    await waitFor(() => {
      expect(screen.getByTestId("replay-current-role")).toHaveTextContent("Tool");
      expect(screen.getByTestId("replay-current-actor")).toHaveTextContent("get_weather_forecast");
      expect(useCanvasStore.getState().activeNodeId).toBe("tool-weather-2");
    });
  });

  it("extracts tool name from error content when agent_name is missing", async () => {
    const user = userEvent.setup();
    const { importConversationZip } = await import("@/lib/api");

    useCanvasStore.getState().setNodes([
      {
        id: "tool-weather-3",
        type: "tool",
        position: { x: 0, y: 0 },
        data: {
          id: "tool-weather-3",
          name: "get_weather_forecast",
          code: "def get_weather_forecast(city: str): return city",
        },
      } as any,
    ]);

    vi.mocked(importConversationZip).mockResolvedValue({
      id: "conv-1",
      canvas_id: "canvas-1",
      name: "Tool Replay Error",
      status: "active",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
      messages: [
        {
          id: "m1",
          conversation_id: "conv-1",
          role: "assistant",
          content: "Execution error in get_weather_forecast: timeout",
          agent_name: null,
          node_id: null,
          event_type: "tool_result",
          created_at: "2026-01-01T00:00:02Z",
        },
      ],
    } as any);

    render(<ConversationReplayPanel />);

    await user.click(screen.getByTestId("replay-launcher-button"));

    const file = new File(["zipcontent"], "conversation.zip", { type: "application/zip" });
    const input = screen.getByTestId("replay-file-input");
    await user.upload(input, file);

    await waitFor(() => {
      expect(screen.getByTestId("replay-current-role")).toHaveTextContent("Tool");
      expect(useCanvasStore.getState().activeNodeId).toBe("tool-weather-3");
    });
  });

  it("lists existing canvas conversations and loads selected replay", async () => {
    const user = userEvent.setup();
    const { listConversations, getConversation } = await import("@/lib/api");

    vi.mocked(listConversations).mockResolvedValue([
      {
        id: "conv-1",
        canvas_id: "canvas-1",
        name: "Weather Analysis",
        status: "active",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:05:00Z",
      },
      {
        id: "conv-2",
        canvas_id: "canvas-1",
        name: "Finance Review",
        status: "active",
        created_at: "2026-01-02T00:00:00Z",
        updated_at: "2026-01-02T00:05:00Z",
      },
    ] as any);

    vi.mocked(getConversation).mockResolvedValue({
      id: "conv-2",
      canvas_id: "canvas-1",
      name: "Finance Review",
      status: "active",
      created_at: "2026-01-02T00:00:00Z",
      updated_at: "2026-01-02T00:05:00Z",
      messages: [
        {
          id: "m1",
          conversation_id: "conv-2",
          role: "user",
          content: "Summarize risk",
          node_id: null,
          created_at: "2026-01-02T00:00:01Z",
        },
        {
          id: "m2",
          conversation_id: "conv-2",
          role: "assistant",
          content: "Risk is moderate",
          agent_name: "Finance Agent",
          node_id: "agent-finance",
          created_at: "2026-01-02T00:00:02Z",
        },
      ],
    } as any);

    render(<ConversationReplayPanel />);

    await user.click(screen.getByTestId("replay-launcher-button"));
    await user.click(screen.getByTestId("replay-browse-button"));

    await waitFor(() => {
      expect(listConversations).toHaveBeenCalledWith("canvas-1");
      expect(screen.getByText("Weather Analysis")).toBeInTheDocument();
      expect(screen.getByText("Finance Review")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Finance Review" }));

    await waitFor(() => {
      expect(getConversation).toHaveBeenCalledWith("canvas-1", "conv-2");
      expect(screen.getByTestId("replay-current-message")).toHaveTextContent("Summarize risk");
      expect(screen.getByTestId("replay-conversation-name")).toHaveTextContent("Finance Review");
    });

    await user.click(screen.getByTestId("replay-next-button"));

    await waitFor(() => {
      expect(screen.getByTestId("replay-current-actor")).toHaveTextContent("Finance Agent");
      expect(useCanvasStore.getState().activeNodeId).toBe("agent-finance");
    });
  });

  it("jumps with timeline slider and supports keyboard navigation", async () => {
    const user = userEvent.setup();
    const { importConversationZip } = await import("@/lib/api");

    vi.mocked(importConversationZip).mockResolvedValue({
      id: "conv-1",
      canvas_id: "canvas-1",
      name: "Replay Keyboard",
      status: "active",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
      messages: [
        {
          id: "m1",
          conversation_id: "conv-1",
          role: "user",
          content: "Step one",
          node_id: null,
          created_at: "2026-01-01T00:00:01Z",
        },
        {
          id: "m2",
          conversation_id: "conv-1",
          role: "assistant",
          content: "Step two",
          node_id: "agent-1",
          created_at: "2026-01-01T00:00:02Z",
        },
        {
          id: "m3",
          conversation_id: "conv-1",
          role: "assistant",
          content: "Step three",
          node_id: "agent-1",
          created_at: "2026-01-01T00:00:03Z",
        },
      ],
    } as any);

    render(<ConversationReplayPanel />);

    await user.click(screen.getByTestId("replay-launcher-button"));

    const file = new File(["zipcontent"], "conversation.zip", { type: "application/zip" });
    const input = screen.getByTestId("replay-file-input");
    await user.upload(input, file);

    await waitFor(() => {
      expect(screen.getByTestId("replay-current-message")).toHaveTextContent("Step one");
      expect(screen.getByTestId("replay-step-indicator")).toHaveTextContent("1/3");
    });

    const slider = screen.getByTestId("replay-timeline-slider");
    fireEvent.change(slider, { target: { value: "2" } });

    await waitFor(() => {
      expect(screen.getByTestId("replay-current-message")).toHaveTextContent("Step three");
      expect(screen.getByTestId("replay-step-indicator")).toHaveTextContent("3/3");
    });

    fireEvent.keyDown(window, { key: "Home" });

    await waitFor(() => {
      expect(screen.getByTestId("replay-current-message")).toHaveTextContent("Step one");
      expect(screen.getByTestId("replay-step-indicator")).toHaveTextContent("1/3");
    });

    fireEvent.keyDown(window, { key: "ArrowRight" });

    await waitFor(() => {
      expect(screen.getByTestId("replay-current-message")).toHaveTextContent("Step two");
      expect(screen.getByTestId("replay-step-indicator")).toHaveTextContent("2/3");
    });

    fireEvent.keyDown(window, { key: "ArrowLeft" });

    await waitFor(() => {
      expect(screen.getByTestId("replay-current-message")).toHaveTextContent("Step one");
      expect(screen.getByTestId("replay-step-indicator")).toHaveTextContent("1/3");
    });
  });

  it("autoplays replay messages and stops at the end", async () => {
    const user = userEvent.setup();
    const { importConversationZip } = await import("@/lib/api");

    vi.mocked(importConversationZip).mockResolvedValue({
      id: "conv-1",
      canvas_id: "canvas-1",
      name: "Replay Autoplay",
      status: "active",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
      messages: [
        {
          id: "m1",
          conversation_id: "conv-1",
          role: "user",
          content: "Start",
          node_id: null,
          created_at: "2026-01-01T00:00:01Z",
        },
        {
          id: "m2",
          conversation_id: "conv-1",
          role: "assistant",
          content: "Middle",
          node_id: "agent-1",
          created_at: "2026-01-01T00:00:02Z",
        },
        {
          id: "m3",
          conversation_id: "conv-1",
          role: "assistant",
          content: "End",
          node_id: "agent-1",
          created_at: "2026-01-01T00:00:03Z",
        },
      ],
    } as any);

    render(<ConversationReplayPanel />);

    await user.click(screen.getByTestId("replay-launcher-button"));

    const file = new File(["zipcontent"], "conversation.zip", { type: "application/zip" });
    const input = screen.getByTestId("replay-file-input");
    await user.upload(input, file);

    await waitFor(() => {
      expect(screen.getByTestId("replay-current-message")).toHaveTextContent("Start");
    });

    await user.click(screen.getByTestId("replay-play-button"));

    await waitFor(() => {
      expect(screen.getByTestId("replay-current-message")).toHaveTextContent("End");
      expect(screen.getByTestId("replay-step-indicator")).toHaveTextContent("3/3");
      expect(screen.getByTestId("replay-play-button")).toHaveTextContent("Play");
    }, { timeout: 5000 });
  });

  it("renders timeline ticks and jumps when a tick is clicked", async () => {
    const user = userEvent.setup();
    const { importConversationZip } = await import("@/lib/api");

    vi.mocked(importConversationZip).mockResolvedValue({
      id: "conv-1",
      canvas_id: "canvas-1",
      name: "Replay Timeline Rail",
      status: "active",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
      messages: [
        {
          id: "m1",
          conversation_id: "conv-1",
          role: "user",
          content: "User asks",
          node_id: null,
          created_at: "2026-01-01T00:00:01Z",
        },
        {
          id: "m2",
          conversation_id: "conv-1",
          role: "assistant",
          content: "Assistant responds",
          node_id: "agent-1",
          created_at: "2026-01-01T00:00:02Z",
        },
        {
          id: "m3",
          conversation_id: "conv-1",
          role: "tool",
          event_type: "tool_result",
          content: "Execution error in calc_tool: timeout",
          node_id: "tool-1",
          created_at: "2026-01-01T00:00:03Z",
        },
      ],
    } as any);

    render(<ConversationReplayPanel />);

    await user.click(screen.getByTestId("replay-launcher-button"));

    const file = new File(["zipcontent"], "conversation.zip", { type: "application/zip" });
    const input = screen.getByTestId("replay-file-input");
    await user.upload(input, file);

    await waitFor(() => {
      expect(screen.getByTestId("replay-timeline-rail")).toBeInTheDocument();
      expect(screen.getAllByTestId(/^replay-timeline-tick-/)).toHaveLength(3);
    });

    await user.click(screen.getByTestId("replay-timeline-tick-2"));

    await waitFor(() => {
      expect(screen.getByTestId("replay-current-message")).toHaveTextContent("Execution error in calc_tool: timeout");
      expect(screen.getByTestId("replay-step-indicator")).toHaveTextContent("3/3");
    });
  });

  it("filters and sorts conversation list with metadata badges", async () => {
    const user = userEvent.setup();
    const { listConversations } = await import("@/lib/api");

    vi.mocked(listConversations).mockResolvedValue([
      {
        id: "conv-1",
        canvas_id: "canvas-1",
        name: "Alpha Notes",
        status: "active",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:05:00Z",
      },
      {
        id: "conv-2",
        canvas_id: "canvas-1",
        name: "Zulu Plan",
        status: "completed",
        created_at: "2026-01-02T00:00:00Z",
        updated_at: "2026-01-03T00:05:00Z",
      },
      {
        id: "conv-3",
        canvas_id: "canvas-1",
        name: "Bravo Risk",
        status: "error",
        created_at: "2026-01-02T00:00:00Z",
        updated_at: "2026-01-02T00:05:00Z",
      },
    ] as any);

    render(<ConversationReplayPanel />);

    await user.click(screen.getByTestId("replay-launcher-button"));
    await user.click(screen.getByTestId("replay-browse-button"));

    await waitFor(() => {
      expect(screen.getByTestId("replay-conversation-search")).toBeInTheDocument();
      expect(screen.getByTestId("replay-conversation-sort")).toBeInTheDocument();
    });

    const items = screen.getAllByTestId("replay-conversation-item-name");
    expect(items[0]).toHaveTextContent("Zulu Plan");
    expect(items[1]).toHaveTextContent("Bravo Risk");
    expect(items[2]).toHaveTextContent("Alpha Notes");

    expect(screen.getByTestId("replay-conversation-item-status-conv-2")).toHaveTextContent("completed");
    expect(screen.getByTestId("replay-conversation-item-updated-conv-2")).toBeInTheDocument();

    await user.type(screen.getByTestId("replay-conversation-search"), "bravo");

    await waitFor(() => {
      const filteredItems = screen.getAllByTestId("replay-conversation-item-name");
      expect(filteredItems).toHaveLength(1);
      expect(filteredItems[0]).toHaveTextContent("Bravo Risk");
    });

    await user.clear(screen.getByTestId("replay-conversation-search"));
    await user.selectOptions(screen.getByTestId("replay-conversation-sort"), "name_asc");

    await waitFor(() => {
      const sortedByName = screen.getAllByTestId("replay-conversation-item-name");
      expect(sortedByName[0]).toHaveTextContent("Alpha Notes");
      expect(sortedByName[1]).toHaveTextContent("Bravo Risk");
      expect(sortedByName[2]).toHaveTextContent("Zulu Plan");
    });
  });
});
