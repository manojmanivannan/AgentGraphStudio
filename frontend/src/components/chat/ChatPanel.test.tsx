import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useCanvasStore } from "@/store/canvasStore";
import { ChatPanel } from "./ChatPanel";
import { FakeWebSocket } from "@/test/mocks/websocket";
import { server } from "@/test/mocks/server";
import { http, HttpResponse } from "msw";

// Silence scrollIntoView — not implemented in jsdom
beforeAll(() => {
  HTMLElement.prototype.scrollIntoView = vi.fn();
});

beforeEach(() => {
  useCanvasStore.getState().reset();
  useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");
  vi.stubGlobal("WebSocket", FakeWebSocket);
  FakeWebSocket.reset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// Helper: render ChatPanel, open it, and wait for initial conversation list load
async function setup() {
  const utils = render(<ChatPanel />);
  // Open the chat panel first
  await act(async () => {
    await userEvent.click(screen.getByTestId("chat-toggle"));
  });
  // Wait for listConversations to settle
  await waitFor(() =>
    expect(screen.queryByTestId("conversation-selector")).toBeInTheDocument()
  );
  return utils;
}

// Helper: create a new conversation via the UI and return its id from state
async function createConversation(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByTestId("conversation-selector"));
  await user.click(screen.getByTestId("new-conversation-button"));
  // Wait for the conversation to be created and the dropdown to close
  await waitFor(() =>
    expect(screen.queryByTestId("new-conversation-button")).not.toBeInTheDocument()
  );
}

// Helper: type a message and press Enter to send
async function sendMessage(
  user: ReturnType<typeof userEvent.setup>,
  message: string
) {
  const input = screen.getByTestId("chat-input");
  await user.type(input, message);
  await user.keyboard("{Enter}");
}

// Helper: wait for the WebSocket to receive the initial prompt
async function waitForWsConnected() {
  await waitFor(() => {
    const ws = FakeWebSocket.lastInstance();
    expect(ws?.sentMessages.length).toBeGreaterThan(0);
  });
}

describe("ChatPanel", () => {
  describe("conversation management", () => {
    it("calls listConversations on mount and shows selector", async () => {
      // Override handler to return one existing conversation
      server.use(
        http.get(
          "http://localhost:8000/api/canvases/canvas-1/conversations",
          () =>
            HttpResponse.json([
              {
                id: "conv-existing",
                canvas_id: "canvas-1",
                name: "Old Chat",
                status: "active",
                created_at: "2024-01-01T00:00:00Z",
                updated_at: "2024-01-01T00:00:00Z",
              },
            ])
        )
      );

      await setup();

      await act(async () => {
        await userEvent.click(screen.getByTestId("conversation-selector"));
      });
      expect(screen.getByText("Old Chat")).toBeInTheDocument();
    });

    it("creates a new conversation when New Conversation is clicked", async () => {
      const user = userEvent.setup();
      await setup();

      await createConversation(user);

      // After creation, selector should show the conversation name
      expect(screen.getByText("New Conversation")).toBeInTheDocument();
    });

    it("loads message history when an existing conversation is selected", async () => {
      server.use(
        http.get(
          "http://localhost:8000/api/canvases/canvas-1/conversations",
          () =>
            HttpResponse.json([
              {
                id: "conv-a",
                canvas_id: "canvas-1",
                name: "Chat A",
                status: "active",
                created_at: "2024-01-01T00:00:00Z",
                updated_at: "2024-01-01T00:00:00Z",
              },
            ])
        ),
        http.get(
          "http://localhost:8000/api/canvases/canvas-1/conversations/conv-a",
          () =>
            HttpResponse.json({
              id: "conv-a",
              canvas_id: "canvas-1",
              name: "Chat A",
              status: "active",
              created_at: "2024-01-01T00:00:00Z",
              updated_at: "2024-01-01T00:00:00Z",
              messages: [
                {
                  id: "m1",
                  conversation_id: "conv-a",
                  role: "user",
                  content: "Hello from history",
                  created_at: "2024-01-01T00:00:00Z",
                },
              ],
            })
        )
      );

      const user = userEvent.setup();
      await setup();

      await user.click(screen.getByTestId("conversation-selector"));
      await user.click(screen.getByText("Chat A"));

      await waitFor(() =>
        expect(screen.getByText("Hello from history")).toBeInTheDocument()
      );
    });

    it("removes a deleted conversation from the list", async () => {
      server.use(
        http.get(
          "http://localhost:8000/api/canvases/canvas-1/conversations",
          () =>
            HttpResponse.json([
              {
                id: "conv-del",
                canvas_id: "canvas-1",
                name: "To Delete",
                status: "active",
                created_at: "2024-01-01T00:00:00Z",
                updated_at: "2024-01-01T00:00:00Z",
              },
            ])
        )
      );

      const user = userEvent.setup();
      await setup();

      await user.click(screen.getByTestId("conversation-selector"));
      await user.click(screen.getByTestId("delete-conversation-button"));

      await waitFor(() =>
        expect(screen.queryByText("To Delete")).not.toBeInTheDocument()
      );
    });
  });

  describe("send and WebSocket lifecycle", () => {
    it("shows the user message immediately on send", async () => {
      const user = userEvent.setup();
      await setup();
      await createConversation(user);

      await sendMessage(user, "Hello world");

      await waitFor(() =>
        expect(screen.getByText("Hello world")).toBeInTheDocument()
      );
    });

    it("disables the send button while running", async () => {
      const user = userEvent.setup();
      await setup();
      await createConversation(user);

      await sendMessage(user, "Run it");

      await waitForWsConnected();

      // While WebSocket is open and running, send button becomes stop-button
      expect(screen.getByTestId("stop-button")).toBeInTheDocument();
      // Input should be disabled while running
      expect(screen.getByTestId("chat-input")).toBeDisabled();
    });

    it("disables the input when canvasId is null", async () => {
      useCanvasStore.getState().reset(); // clears canvasId
      const user = userEvent.setup();
      render(<ChatPanel />);
      await user.click(screen.getByTestId("chat-toggle"));

      expect(screen.getByTestId("chat-input")).toBeDisabled();
    });

    it("sends to an existing conversation without creating a new one", async () => {
      const user = userEvent.setup();
      await setup();
      await createConversation(user);

      // Track POST calls to conversations
      const createCalls: string[] = [];
      server.use(
        http.post(
          "http://localhost:8000/api/canvases/canvas-1/conversations",
          async ({ request }) => {
            createCalls.push(await request.text());
            return HttpResponse.json(
              {
                id: "conv-new",
                canvas_id: "canvas-1",
                name: "New Conversation",
                status: "active",
                created_at: "2024-01-01T00:00:00Z",
                updated_at: "2024-01-01T00:00:00Z",
                messages: [],
              },
              { status: 201 }
            );
          }
        )
      );

      const initialCallCount = createCalls.length;
      await sendMessage(user, "Second message");
      await waitForWsConnected();

      // Should NOT have created another conversation
      expect(createCalls.length).toBe(initialCallCount);
    });
  });

  describe("streaming event rendering", () => {
    async function setupAndSend() {
      const user = userEvent.setup();
      await setup();
      await createConversation(user);
      await sendMessage(user, "Test");
      await waitForWsConnected();
      return FakeWebSocket.lastInstance()!;
    }

    it("renders agent_start as a system message", async () => {
      const ws = await setupAndSend();

      act(() => {
        ws.simulateMessage({
          type: "agent_start",
          agent: "Orchestrator",
          node_id: "node-1",
        });
      });

      await waitFor(() =>
        expect(screen.getByText("Orchestrator is working...")).toBeInTheDocument()
      );
    });

    it("renders thought events collapsed by default", async () => {
      const ws = await setupAndSend();

      act(() => {
        ws.simulateMessage({
          type: "thought",
          agent: "Researcher",
          content: "Deep thoughts here",
          node_id: "node-1",
        });
      });

      await waitFor(() =>
        expect(screen.getByText("Thinking...")).toBeInTheDocument()
      );
      // The content should not be visible (collapsed)
      expect(screen.queryByText("Deep thoughts here")).not.toBeInTheDocument();
    });

    it("expands a thought message when clicked", async () => {
      const ws = await setupAndSend();

      act(() => {
        ws.simulateMessage({
          type: "thought",
          agent: "Researcher",
          content: "Deep thoughts here",
          node_id: "node-1",
        });
      });

      await waitFor(() =>
        expect(screen.getByText("Thinking...")).toBeInTheDocument()
      );

      await userEvent.click(screen.getByText("Thinking..."));

      await waitFor(() =>
        expect(screen.getByText("Deep thoughts here")).toBeInTheDocument()
      );
    });

    it("collapses an expanded thought when the hide button is clicked", async () => {
      const ws = await setupAndSend();

      act(() => {
        ws.simulateMessage({
          type: "thought",
          agent: "Researcher",
          content: "Deep thoughts here",
          node_id: "node-1",
        });
      });

      await waitFor(() => expect(screen.getByText("Thinking...")).toBeInTheDocument());

      // Expand it
      await userEvent.click(screen.getByText("Thinking..."));
      await waitFor(() => expect(screen.getByText("Deep thoughts here")).toBeInTheDocument());

      // Collapse it via the "Hide thought" button
      await userEvent.click(screen.getByText("Hide thought"));
      await waitFor(() =>
        expect(screen.queryByText("Deep thoughts here")).not.toBeInTheDocument()
      );
    });

    it("renders handoff as a system message", async () => {
      const ws = await setupAndSend();

      act(() => {
        ws.simulateMessage({
          type: "handoff",
          from: "Orchestrator",
          to: "Researcher",
          node_id: "node-1",
        });
      });

      await waitFor(() =>
        expect(screen.getByText("Delegating to Researcher...")).toBeInTheDocument()
      );
    });

    it("renders tool_result as an assistant message", async () => {
      const ws = await setupAndSend();

      act(() => {
        ws.simulateMessage({
          type: "tool_result",
          agent: "Researcher",
          tool: "WebSearch",
          output: "Search results here",
          node_id: "node-1",
        });
      });

      await waitFor(() =>
        expect(screen.getByText("Search results here")).toBeInTheDocument()
      );
    });

    it("renders final_answer as an assistant message", async () => {
      const ws = await setupAndSend();

      act(() => {
        ws.simulateMessage({
          type: "final_answer",
          agent: "Researcher",
          content: "The final answer is 42",
          node_id: "node-1",
        });
      });

      await waitFor(() =>
        expect(screen.getByText("The final answer is 42")).toBeInTheDocument()
      );
    });

    it("run_complete re-enables the send button", async () => {
      const ws = await setupAndSend();

      act(() => {
        ws.simulateMessage({ type: "run_complete", result: "" });
      });

      await waitFor(() =>
        expect(screen.queryByTestId("stop-button")).not.toBeInTheDocument()
      );
      expect(screen.getByTestId("send-button")).toBeInTheDocument();
    });

    it("renders an error event as a red system message and ends running", async () => {
      const ws = await setupAndSend();

      act(() => {
        ws.simulateMessage({
          type: "error",
          message: "Something went wrong",
        });
      });

      await waitFor(() =>
        expect(screen.getByText("Something went wrong")).toBeInTheDocument()
      );
      // Running state should end
      await waitFor(() =>
        expect(screen.queryByTestId("stop-button")).not.toBeInTheDocument()
      );
    });
  });

  describe("stop button", () => {
    it("is visible while running", async () => {
      const user = userEvent.setup();
      await setup();
      await createConversation(user);
      await sendMessage(user, "Go");
      await waitForWsConnected();

      expect(screen.getByTestId("stop-button")).toBeInTheDocument();
    });

    it("closes the WebSocket when clicked", async () => {
      const user = userEvent.setup();
      await setup();
      await createConversation(user);
      await sendMessage(user, "Go");
      await waitForWsConnected();

      const ws = FakeWebSocket.lastInstance()!;
      await user.click(screen.getByTestId("stop-button"));

      expect(ws.closed).toBe(true);
    });
  });
});
