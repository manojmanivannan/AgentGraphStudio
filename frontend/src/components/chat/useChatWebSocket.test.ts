import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useChatWebSocket } from "./useChatWebSocket";
import { FakeWebSocket } from "@/test/mocks/websocket";
import { useCanvasStore } from "@/store/canvasStore";

// Mock the API calls
vi.mock("@/lib/api", () => ({
  getActiveRun: vi.fn().mockResolvedValue(null),
  abortRun: vi.fn().mockResolvedValue({}),
  submitInterruptResponse: vi.fn().mockResolvedValue({}),
  getConversationById: vi.fn().mockResolvedValue({ id: "c1", name: "Mock Conv" }),
}));

describe("useChatWebSocket", () => {
  beforeEach(() => {
    useCanvasStore.getState().reset();
    FakeWebSocket.reset();
    vi.stubGlobal("WebSocket", FakeWebSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  const setup = (props: any = {}) => {
    return renderHook(() => useChatWebSocket({
      conversation_id: "c1",
      loadSidebar: vi.fn(),
      setConversationName: vi.fn(),
      setConversations: vi.fn(),
      chatInputRef: { current: null },
      inlineInputRef: { current: null },
      loadingConv: false,
      ...props
    }));
  };

  it("initializes with default state", () => {
    const { result } = setup();
    expect(result.current.messages).toEqual([]);
    expect(result.current.running).toBe(false);
    expect(result.current.activeInterrupt).toBeNull();
  });

  it("connects and handles run queued", async () => {
    const { result } = setup();
    
    act(() => {
      result.current.connectAndRun("c1", { prompt: "Hello" });
    });

    expect(result.current.running).toBe(true);
    // User message is added locally
    expect(result.current.messages.length).toBe(1);
    expect(result.current.messages[0].content).toBe("Hello");
    expect(result.current.messages[0].role).toBe("user");

    const ws = FakeWebSocket.lastInstance();
    expect(ws).toBeDefined();

    // Simulate run_queued event
    act(() => {
      ws!.simulateMessage({
        type: "run_queued",
        run_id: "r1"
      });
    });

    // Expect still running
    expect(result.current.running).toBe(true);
  });

  it("handles run complete", async () => {
    const loadSidebar = vi.fn();
    const { result } = setup({ loadSidebar });
    
    act(() => {
      result.current.connectAndRun("c1", { prompt: "Test" });
    });

    const ws = FakeWebSocket.lastInstance();
    act(() => {
      ws!.simulateMessage({
        type: "run_complete",
        run_id: "r1"
      });
    });

    expect(result.current.running).toBe(false);
    expect(loadSidebar).toHaveBeenCalled();
  });

  it("handles error events", () => {
    const { result } = setup();
    
    act(() => {
      result.current.connectAndRun("c1", { prompt: "Test" });
    });

    const ws = FakeWebSocket.lastInstance();
    act(() => {
      ws!.simulateMessage({
        type: "error",
        error: "Something failed"
      });
    });

    expect(result.current.running).toBe(false);
    expect(result.current.messages.length).toBe(2); // user msg + error msg
    expect(result.current.messages[1].event_type).toBe("error");
  });
  
  it("handles human input interrupt", () => {
    const { result } = setup();
    
    act(() => {
      result.current.connectAndRun("c1", { prompt: "Test" });
    });

    const ws = FakeWebSocket.lastInstance();
    act(() => {
      ws!.simulateMessage({
        type: "human_input_request",
        request_id: "req1",
        question: "What is your name?"
      });
    });

    expect(result.current.activeInterrupt).toEqual(expect.objectContaining({
      type: "human_input",
      request_id: "req1",
      question: "What is your name?"
    }));
  });
});
