import { test as base, expect } from "@playwright/test";
import type { APIRequestContext } from "@playwright/test";

const API_BASE = "http://localhost:8000/api";

export interface WorkflowNodeIds {
  canvasId: string;
  routerId: string;
  researcherId: string;
  summariserId: string;
  toolId: string;
}

function uuid(): string {
  return crypto.randomUUID();
}

async function seedWorkflow(
  request: APIRequestContext
): Promise<WorkflowNodeIds> {
  // Create canvas
  const createRes = await request.post(`${API_BASE}/canvases`, {
    data: { name: "E2E Workflow Canvas" },
  });
  expect(createRes.ok()).toBeTruthy();
  const canvas = await createRes.json();
  const canvasId: string = canvas.id;

  // Generate stable node IDs for this fixture instance
  const routerId = uuid();
  const researcherId = uuid();
  const summariserId = uuid();
  const toolId = uuid();

  const edgeOrchResearcher = uuid();
  const edgeOrchSummariser = uuid();
  const edgeResearcherTool = uuid();

  const stubCode = [
    "def run(query: str) -> str:",
    '    """Web search stub"""',
    "    return f'Results for: {query}'",
  ].join("\n");

  // Save workflow into the canvas
  const saveRes = await request.put(`${API_BASE}/canvases/${canvasId}`, {
    data: {
      name: "E2E Workflow Canvas",
      nodes: {
        agents: [
          {
            id: routerId,
            name: "Orchestrator",
            role: "Orchestrates the workflow",
            instructions: "Route tasks to appropriate workers",
            model_name: "ollama:llama3.1",
            agent_type: "router",
            position_x: 100,
            position_y: 100,
          },
          {
            id: researcherId,
            name: "Researcher",
            role: "Researches topics",
            instructions: "Search and gather information",
            model_name: "ollama:llama3.1",
            agent_type: "worker",
            position_x: 300,
            position_y: 50,
          },
          {
            id: summariserId,
            name: "Summariser",
            role: "Summarises content",
            instructions: "Produce concise summaries",
            model_name: "ollama:llama3.1",
            agent_type: "worker",
            position_x: 300,
            position_y: 200,
          },
        ],
        tools: [
          {
            id: toolId,
            name: "WebSearch",
            code: stubCode,
            position_x: 500,
            position_y: 50,
          },
        ],
      },
      edges: [
        {
          id: edgeOrchResearcher,
          source_node_id: routerId,
          target_node_id: researcherId,
          edge_type: "handoff",
        },
        {
          id: edgeOrchSummariser,
          source_node_id: routerId,
          target_node_id: summariserId,
          edge_type: "handoff",
        },
        {
          id: edgeResearcherTool,
          source_node_id: researcherId,
          target_node_id: toolId,
          edge_type: "tool_access",
        },
      ],
    },
  });
  expect(saveRes.ok()).toBeTruthy();

  return { canvasId, routerId, researcherId, summariserId, toolId };
}

export type CanvasFixture = {
  canvasWithWorkflow: WorkflowNodeIds;
};

export const test = base.extend<CanvasFixture>({
  canvasWithWorkflow: async ({ page, request }, use) => {
    const nodeIds = await seedWorkflow(request);

    // Navigate directly to the canvas editor via the deep-link URL param
    await page.goto(`/?canvas=${nodeIds.canvasId}`);
    await expect(page.locator(".react-flow")).toBeVisible({ timeout: 10_000 });

    // Open the chat panel so tests can interact with the conversation selector
    await page.getByTestId("chat-toggle").click();

    await use(nodeIds);
  },
});

export { expect };
