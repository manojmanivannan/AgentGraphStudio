import { test as canvasTest, type CanvasFixture } from "./canvas";
import type { WorkflowNodeIds } from "./canvas";
import type { WebSocketRoute } from "@playwright/test";

export interface WsHelper {
  triggerRun: (nodeIds: WorkflowNodeIds) => Promise<void>;
}

export type WsFixture = {
  wsFixture: WsHelper;
};

export const test = canvasTest.extend<WsFixture>({
  wsFixture: async ({ page }, use) => {
    const helper: WsHelper = {
      triggerRun: async (nodeIds: WorkflowNodeIds) => {
        // Poll until the WebSocket route fires (page sends a message)
        while (!(page as any).__wsRoute) {
          await new Promise((r) => setTimeout(r, 20));
        }
        const route: WebSocketRoute = (page as any).__wsRoute;

        const events = [
          { type: "run_start", canvas_id: nodeIds.canvasId },
          { type: "agent_start", agent: "Orchestrator", node_id: nodeIds.routerId },
          { type: "handoff", from: "Orchestrator", to: "Researcher", node_id: nodeIds.routerId },
          { type: "agent_start", agent: "Researcher", node_id: nodeIds.researcherId },
          { type: "thought", agent: "Researcher", content: "I should search for this topic.", node_id: nodeIds.researcherId },
          { type: "tool_call", agent: "Researcher", tool: "WebSearch", input: { query: "test query" }, node_id: nodeIds.researcherId },
          { type: "tool_result", agent: "Researcher", tool: "WebSearch", output: "Results for: test query", node_id: nodeIds.researcherId },
          { type: "final_answer", agent: "Researcher", content: "Test answer", node_id: nodeIds.researcherId },
          { type: "run_complete", result: "Test answer" },
        ];
        for (const event of events) {
          route.send(JSON.stringify(event));
          await new Promise((r) => setTimeout(r, 30));
        }
      },
    };

    await use(helper);
  },
});

export { expect } from "@playwright/test";
export type { WorkflowNodeIds };
