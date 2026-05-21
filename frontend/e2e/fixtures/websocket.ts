import { test as base } from "@playwright/test";
import type { WebSocketRoute } from "@playwright/test";
import { test as canvasTest, type CanvasFixture } from "./canvas";
import type { WorkflowNodeIds } from "./canvas";

const WS_URL_PATTERN = "ws://localhost:8000/ws/conversations/*/run";

export interface WsHelper {
  /** Stream all 9 execution events through the intercepted WebSocket. */
  triggerRun: (nodeIds: WorkflowNodeIds) => Promise<void>;
}

export type WsFixture = {
  wsFixture: WsHelper;
};

export const test = canvasTest.extend<WsFixture>({
  wsFixture: async ({ page }, use) => {
    let wsRoute: WebSocketRoute | null = null;
    let resolveConnected!: () => void;
    const connected = new Promise<void>((resolve) => {
      resolveConnected = resolve;
    });

    await page.routeWebSocket(WS_URL_PATTERN, (route) => {
      wsRoute = route;
      resolveConnected();
      // Absorb messages from the client so they don't cause errors
      route.onMessage(() => {});
    });

    const helper: WsHelper = {
      triggerRun: async (nodeIds: WorkflowNodeIds) => {
        // Wait for the frontend to actually open a WebSocket connection
        await connected;
        const ws = wsRoute!;

        const events = [
          { type: "run_start", canvas_id: nodeIds.canvasId },
          {
            type: "agent_start",
            agent: "Orchestrator",
            node_id: nodeIds.routerId,
          },
          {
            type: "handoff",
            from: "Orchestrator",
            to: "Researcher",
            node_id: nodeIds.routerId,
          },
          {
            type: "agent_start",
            agent: "Researcher",
            node_id: nodeIds.researcherId,
          },
          {
            type: "thought",
            agent: "Researcher",
            content: "I should search for this topic.",
            node_id: nodeIds.researcherId,
          },
          {
            type: "tool_call",
            agent: "Researcher",
            tool: "WebSearch",
            input: { query: "test query" },
            node_id: nodeIds.researcherId,
          },
          {
            type: "tool_result",
            agent: "Researcher",
            tool: "WebSearch",
            output: "Results for: test query",
            node_id: nodeIds.researcherId,
          },
          {
            type: "final_answer",
            agent: "Researcher",
            content: "Test answer",
            node_id: nodeIds.researcherId,
          },
          { type: "run_complete", result: "Test answer" },
        ];

        for (const event of events) {
          ws.send(JSON.stringify(event));
          // Small delay to let the UI process each event
          await new Promise((r) => setTimeout(r, 30));
        }
      },
    };

    await use(helper);
  },
});

export { expect } from "@playwright/test";
export type { WorkflowNodeIds };
