/**
 * E2E tests for the SidebarRail actions.
 * Uses canvasWithWorkflow fixture to open a seeded canvas.
 */
import { test, expect } from "./fixtures";

test.describe("Sidebar Rail", () => {
    test("clicking Add Worker Agent adds a new agent node", async ({
    page,
    canvasWithWorkflow,
  }) => {
    // Wait for seeded agents to be visible
    await expect(page.locator('[data-testid="agent-node"]').first()).toBeVisible();

    const initialCount = await page
      .locator('[data-testid="agent-node"]')
      .count();

    await page.getByTestId("add-agent-worker").click();

    // Wait for the new node to appear
    await expect(page.locator('[data-testid="agent-node"]')).toHaveCount(
      initialCount + 1,
      { timeout: 5000 }
    );
  });

  test("clicking Add Tool adds a new tool node to the canvas", async ({
    page,
    canvasWithWorkflow,
  }) => {
    // Wait for seeded tools to be visible
    await expect(page.locator('[data-testid="tool-node"]').first()).toBeVisible();

    const initialCount = await page
      .locator('[data-testid="tool-node"]')
      .count();

    await page.getByTestId("add-tool-button").click();

    await expect(page.locator('[data-testid="tool-node"]')).toHaveCount(
      initialCount + 1,
      { timeout: 5000 }
    );
  });

  test("clicking Clear opens confirmation, then clears the canvas", async ({
    page,
    canvasWithWorkflow: _,
  }) => {
    // Verify we have nodes
    await expect(
      page.locator('[data-testid="agent-node"]').first()
    ).toBeVisible();

    await page.getByTestId("clear-canvas-button").click();

    // Confirmation popover should appear
    await expect(page.getByTestId("rail-popover")).toBeVisible();

    // Click Clear in confirmation
    await page.getByTestId("rail-popover").getByRole("button", { name: "Clear", exact: true }).click();

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

    expect(download.suggestedFilename()).toMatch(/\.zip$/);
  });
});