/**
 * E2E tests for canvas node visual states (AgentNode, ToolNode).
 * Uses canvasWithWorkflow and wsFixture.
 */
import { test, expect } from "./fixtures";

test.describe("Canvas Nodes — static rendering", () => {
  test("Orchestrator node is visible with router data attributes", async ({
    page,
    canvasWithWorkflow: { routerId },
  }) => {
    await expect(
      page.locator(
        `[data-testid="agent-node"][data-node-id="${routerId}"][data-agent-type="router"]`
      )
    ).toBeVisible();
  });

  test("Orchestrator node displays a Router badge", async ({
    page,
    canvasWithWorkflow: { routerId },
  }) => {
    const node = page.locator(
      `[data-testid="agent-node"][data-node-id="${routerId}"]`
    );
    await expect(node.getByText("Router")).toBeVisible();
  });

  test("Worker agent nodes display a Worker badge", async ({
    page,
    canvasWithWorkflow: { researcherId },
  }) => {
    const node = page.locator(
      `[data-testid="agent-node"][data-node-id="${researcherId}"]`
    );
    await expect(node.getByText("Worker")).toBeVisible();
  });

  test("WebSearch tool node is visible with correct data-testid", async ({
    page,
    canvasWithWorkflow: { toolId },
  }) => {
    await expect(
      page.locator(`[data-testid="tool-node"][data-node-id="${toolId}"]`)
    ).toBeVisible();
  });

  test("tool node shows the first 3 lines of stub code", async ({
    page,
    canvasWithWorkflow: { toolId },
  }) => {
    const toolNode = page.locator(
      `[data-testid="tool-node"][data-node-id="${toolId}"]`
    );
    await expect(toolNode.getByText(/def run/)).toBeVisible();
  });

  test("clicking an agent node selects it (blue ring visible)", async ({
    page,
    canvasWithWorkflow: { researcherId },
  }) => {
    const node = page.locator(
      `[data-testid="agent-node"][data-node-id="${researcherId}"]`
    );
    await node.click();

    // Selected node has border-blue-500 class applied
    await expect(node).toHaveClass(/border-blue-500/, { timeout: 3000 });
  });
});

test.describe("Canvas Nodes — active pulse during execution", () => {
  test("active node pulses when agent_start event is received", async ({
    page,
    canvasWithWorkflow,
    wsFixture,
  }) => {
    const { routerId, researcherId, summariserId, toolId } = canvasWithWorkflow;

    // Open a conversation and send a message
    await page.getByTestId("conversation-selector").click();
    await page.getByTestId("new-conversation-button").click();
    await page.getByTestId("chat-input").fill("test");
    await page.getByTestId("chat-input").press("Enter");

    // Trigger the mock execution stream
    await wsFixture.triggerRun(canvasWithWorkflow);

    // Router node should pulse during agent_start (Orchestrator)
    // After handoff, Researcher should pulse
    const researcherNode = page.locator(
      `[data-testid="agent-node"][data-node-id="${researcherId}"]`
    );
    await expect(researcherNode).toHaveClass(/animate-pulse/, {
      timeout: 10_000,
    });
  });

  test("no node has animate-pulse after run_complete", async ({
    page,
    canvasWithWorkflow,
    wsFixture,
  }) => {
    await page.getByTestId("conversation-selector").click();
    await page.getByTestId("new-conversation-button").click();
    await page.getByTestId("chat-input").fill("test");
    await page.getByTestId("chat-input").press("Enter");

    await wsFixture.triggerRun(canvasWithWorkflow);

    // Wait for run to complete (send button re-enabled)
    await expect(page.getByTestId("send-button")).toBeEnabled({
      timeout: 15_000,
    });

    // No node should still be pulsing
    await expect(page.locator(".animate-pulse")).toHaveCount(0);
  });
});
