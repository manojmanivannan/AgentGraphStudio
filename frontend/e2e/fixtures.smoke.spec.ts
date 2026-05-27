/**
 * Smoke tests for shared Playwright fixtures.
 * Verifies that canvasWithWorkflow seeds correctly and ReactFlow is visible.
 */
import { test, expect } from "./fixtures";

test.describe("canvasWithWorkflow fixture", () => {
  test("seeds the canvas and opens the editor", async ({
    page,
    canvasWithWorkflow,
  }) => {
    // The fixture already navigated to the canvas editor
    await expect(page.locator(".react-flow")).toBeVisible();

    // All seeded node IDs should be non-empty UUIDs
    const { routerId, researcherId, summariserId, toolId, canvasId } =
      canvasWithWorkflow;
    expect(canvasId).toBeTruthy();
    expect(routerId).toBeTruthy();
    expect(researcherId).toBeTruthy();
    expect(summariserId).toBeTruthy();
    expect(toolId).toBeTruthy();
  });

  test("canvas contains seeded agent nodes", async ({
    page,
    canvasWithWorkflow: { routerId, researcherId, summariserId },
  }) => {
    // Nodes are in the DOM; ReactFlow clips via overflow:hidden so we check
    // attachment rather than visibility to confirm seeding succeeded.
    await expect(
      page.locator(`[data-testid="agent-node"][data-node-id="${routerId}"]`)
    ).toBeAttached();
    await expect(
      page.locator(`[data-testid="agent-node"][data-node-id="${researcherId}"]`)
    ).toBeAttached();
    await expect(
      page.locator(`[data-testid="agent-node"][data-node-id="${summariserId}"]`)
    ).toBeAttached();
  });

  test("canvas contains seeded tool node", async ({
    page,
    canvasWithWorkflow: { toolId },
  }) => {
    await expect(
      page.locator(`[data-testid="tool-node"][data-node-id="${toolId}"]`)
    ).toBeAttached();
  });
});
