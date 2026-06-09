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

  test("clicking an agent node selects it (accent ring visible)", async ({
    page,
    canvasWithWorkflow: { researcherId },
  }) => {
    const node = page.locator(
      `[data-testid="agent-node"][data-node-id="${researcherId}"]`
    );
    await node.click();

    // Selected node gets the accent border via the `selected` prop
    await expect(node).toHaveClass(/border-\[var\(--color-accent\)\]/, { timeout: 3000 });
  });
});

test.describe.skip("Canvas Nodes — active pulse during execution", () => {
  test("active node pulses when agent_start event is received", async ({
    page,
    canvasWithWorkflow,
    wsFixture,
  }) => {
    const { researcherId } = canvasWithWorkflow;

    // Open a conversation and send a message
    await page.getByTestId("conversation-selector").click();
    await page.getByTestId("new-conversation-button").click();
    await page.getByTestId("chat-input").fill("test");
    await page.getByTestId("chat-input").press("Enter");

    const researcherNode = page.locator(
      `[data-testid="agent-node"][data-node-id="${researcherId}"]`
    );

    // Fire triggerRun without awaiting — check the pulse while events stream
    wsFixture.triggerRun(canvasWithWorkflow);

    // The agent_start for Researcher (event 4 of 9) should trigger the pulse
    await expect(researcherNode).toHaveClass(/glow-active-pulse/, {
      timeout: 10_000,
    });
  });

  test("no node has glow-active-pulse after run_complete", async ({
    page,
    canvasWithWorkflow,
    wsFixture,
  }) => {
    await page.getByTestId("conversation-selector").click();
    await page.getByTestId("new-conversation-button").click();
    await page.getByTestId("chat-input").fill("test");
    await page.getByTestId("chat-input").press("Enter");

    await wsFixture.triggerRun(canvasWithWorkflow);

    // Wait for run to complete (send button visible, stop button gone)
    await expect(page.getByTestId("send-button")).toBeVisible({
      timeout: 15_000,
    });

    // No node should still be pulsing
    await expect(page.locator(".glow-active-pulse")).toHaveCount(0);
  });
});
