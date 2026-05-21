/**
 * E2E tests for PropertiesSidebar, AgentEditor, and ToolEditor.
 * Uses canvasWithWorkflow fixture.
 */
import { test, expect } from "./fixtures";

test.describe("Properties Sidebar", () => {
  test("sidebar is collapsed by default (toggle button visible, close button hidden)", async ({
    page,
    canvasWithWorkflow: _,
  }) => {
    await expect(page.getByTestId("properties-toggle")).toBeVisible();
    await expect(page.getByTestId("properties-close")).not.toBeVisible();
  });

  test("clicking the toggle opens the properties panel", async ({
    page,
    canvasWithWorkflow: _,
  }) => {
    await page.getByTestId("properties-toggle").click();

    await expect(page.getByTestId("properties-close")).toBeVisible();
    await expect(
      page.getByText("Select a node to edit its properties")
    ).toBeVisible();
  });

  test("clicking the Orchestrator node opens AgentEditor with its values", async ({
    page,
    canvasWithWorkflow: { routerId },
  }) => {
    await page
      .locator(`[data-testid="agent-node"][data-node-id="${routerId}"]`)
      .click();

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

  test("clicking X closes the properties panel", async ({
    page,
    canvasWithWorkflow: { routerId },
  }) => {
    // Open panel by clicking a node
    await page
      .locator(`[data-testid="agent-node"][data-node-id="${routerId}"]`)
      .click();

    await expect(page.getByTestId("properties-close")).toBeVisible();

    await page.getByTestId("properties-close").click();

    await expect(page.getByTestId("properties-close")).not.toBeVisible();
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
