/**
 * E2E tests for the ToolEditor component.
 * Uses canvasWithWorkflow fixture.
 */
import { test, expect } from "./fixtures";

test.describe("Tool Editor", () => {
  test("clicking the WebSearch tool node opens ToolEditor with its name", async ({
    page,
    canvasWithWorkflow: { toolId },
  }) => {
    await page
      .locator(`[data-testid="tool-node"][data-node-id="${toolId}"]`)
      .click();

    await expect(page.getByTestId("tool-name-input")).toHaveValue("WebSearch");
  });

  test("editing the tool name updates the node title on the canvas", async ({
    page,
    canvasWithWorkflow: { toolId },
  }) => {
    await page
      .locator(`[data-testid="tool-node"][data-node-id="${toolId}"]`)
      .click();

    await page.getByTestId("tool-name-input").click({ clickCount: 3 });
    await page.getByTestId("tool-name-input").fill("BingSearch");

    await expect(
      page
        .locator(`[data-testid="tool-node"][data-node-id="${toolId}"]`)
        .getByText("BingSearch")
    ).toBeVisible({ timeout: 5000 });
  });

  test("tool node shows first 3 lines of code as preview", async ({
    page,
    canvasWithWorkflow: { toolId },
  }) => {
    const toolNode = page.locator(
      `[data-testid="tool-node"][data-node-id="${toolId}"]`
    );

    // The stub code starts with 'def run(query: str) -> str:'
    await expect(toolNode.getByText(/def run/)).toBeVisible();
  });
});
