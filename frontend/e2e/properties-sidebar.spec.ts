/**
 * E2E tests for PropertiesOverlay, AgentEditor, and ToolEditor.
 * Uses canvasWithWorkflow fixture.
 */
import { test, expect } from "./fixtures";

test.describe("Properties Overlay", () => {
  test("properties overlay is hidden when no node is selected", async ({
    page,
    canvasWithWorkflow: _,
  }) => {
    await expect(page.getByTestId("properties-overlay")).not.toBeVisible();
  });

  test("clicking the Orchestrator node opens AgentEditor with its values", async ({
    page,
    canvasWithWorkflow: { routerId },
  }) => {
    await page
      .locator(`[data-testid="agent-node"][data-node-id="${routerId}"]`)
      .click();

    await expect(page.getByTestId("properties-overlay")).toBeVisible();
    await expect(page.getByTestId("agent-name-input")).toHaveValue(
      "Orchestrator"
    );
    await expect(page.getByTestId("agent-type-select")).toHaveValue("router");
  });

  test("editing agent name in the panel updates the node title on the canvas", async ({
    page,
    canvasWithWorkflow: { researcherId },
  }) => {
    // Click the Researcher node to select it
    await page
      .locator(`[data-testid="agent-node"][data-node-id="${researcherId}"]`)
      .click();

    // Clear and type a new name
    await page.getByTestId("agent-name-input").click({ clickCount: 3 });
    await page.getByTestId("agent-name-input").fill("RenamedResearcher");

    // The node title on the canvas should reflect the new name
    await expect(
      page
        .locator(`[data-testid="agent-node"][data-node-id="${researcherId}"]`)
        .getByText("RenamedResearcher")
    ).toBeVisible({ timeout: 5000 });
  });

  test("clicking X closes the properties overlay", async ({
    page,
    canvasWithWorkflow: { routerId },
  }) => {
    // Open overlay by clicking a node
    await page
      .locator(`[data-testid="agent-node"][data-node-id="${routerId}"]`)
      .click();

    await expect(page.getByTestId("properties-overlay")).toBeVisible();

    await page.getByTestId("properties-close").click();

    await expect(page.getByTestId("properties-overlay")).not.toBeVisible();
  });

  test("clicking canvas pane closes the properties overlay", async ({
    page,
    canvasWithWorkflow: { routerId },
  }) => {
    // Open overlay by clicking a node
    await page
      .locator(`[data-testid="agent-node"][data-node-id="${routerId}"]`)
      .click();

    await expect(page.getByTestId("properties-overlay")).toBeVisible();

    // Wait for layout transition to complete before clicking
    await page.waitForTimeout(500);

    // Click an empty area of the canvas pane (top-left corner avoids nodes)
    const pane = page.locator(".react-flow__pane");
    const box = await pane.boundingBox();
    await page.mouse.click(box!.x + 15, box!.y + 15);

    await expect(page.getByTestId("properties-overlay")).not.toBeVisible();
  });

  test("clicking a tool node switches to ToolEditor", async ({
    page,
    canvasWithWorkflow: { researcherId, toolId },
  }) => {
    // First select an agent node
    await page
      .locator(`[data-testid="agent-node"][data-node-id="${researcherId}"]`)
      .click();

    await expect(page.getByTestId("agent-name-input")).toBeVisible();

    // Now click the tool node
    await page
      .locator(`[data-testid="tool-node"][data-node-id="${toolId}"]`)
      .click();

    // Should now show tool editor
    await expect(page.getByTestId("tool-name-input")).toBeVisible({ timeout: 5000 });
    await expect(page.getByTestId("agent-name-input")).not.toBeVisible();
  });
});