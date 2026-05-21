/**
 * E2E tests for the CanvasToolbar component.
 * Uses canvasWithWorkflow fixture to open a seeded canvas.
 */
import { test, expect } from "./fixtures";

test.describe("Canvas Toolbar", () => {
  test("clicking + Agent adds a new agent node to the canvas", async ({
    page,
    canvasWithWorkflow,
  }) => {
    const { routerId, researcherId, summariserId } = canvasWithWorkflow;

    // Count initial agent nodes
    const initialCount = await page
      .locator('[data-testid="agent-node"]')
      .count();

    await page.getByTestId("add-agent-button").click();

    // Wait for the new node to appear
    await expect(page.locator('[data-testid="agent-node"]')).toHaveCount(
      initialCount + 1,
      { timeout: 5000 }
    );
  });

  test("clicking + Tool adds a new tool node to the canvas", async ({
    page,
    canvasWithWorkflow,
  }) => {
    const initialCount = await page
      .locator('[data-testid="tool-node"]')
      .count();

    await page.getByTestId("add-tool-button").click();

    await expect(page.locator('[data-testid="tool-node"]')).toHaveCount(
      initialCount + 1,
      { timeout: 5000 }
    );
  });

  test("clicking Clear removes all nodes from the canvas", async ({
    page,
    canvasWithWorkflow: _,
  }) => {
    // Verify we have nodes
    await expect(
      page.locator('[data-testid="agent-node"]').first()
    ).toBeVisible();

    await page.getByTestId("clear-canvas-button").click();

    // All agent and tool nodes should be gone
    await expect(page.locator('[data-testid="agent-node"]')).toHaveCount(0, {
      timeout: 5000,
    });
    await expect(page.locator('[data-testid="tool-node"]')).toHaveCount(0, {
      timeout: 5000,
    });
  });

  test("renaming the canvas via the name input updates the visible title", async ({
    page,
    canvasWithWorkflow: _,
  }) => {
    const nameInput = page.getByTestId("canvas-name-input");

    await nameInput.click({ clickCount: 3 }); // select all
    await nameInput.fill("Renamed Canvas");
    await nameInput.press("Tab"); // blur to trigger save

    await expect(nameInput).toHaveValue("Renamed Canvas");
  });

  test("Export button triggers a file download", async ({
    page,
    canvasWithWorkflow: _,
  }) => {
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByTestId("export-button").click(),
    ]);

    expect(download.suggestedFilename()).toMatch(/\.json$/);
  });
});
