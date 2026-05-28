import { test, expect } from "@playwright/test";

test.describe("Canvas landing page", () => {
  test("shows Agent Builder heading", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Agent Builder")).toBeVisible();
    await expect(page.getByText("New Canvas")).toBeVisible();
  });

  test("creates a new canvas and enters the editor", async ({ page }) => {
    await page.goto("/");
    await page.getByText("New Canvas").click();

    // After creation, AppShell should be rendered (canvas editor)
    // The canvas view contains a ReactFlow container
    await expect(page.locator(".react-flow")).toBeVisible({ timeout: 10_000 });
  });

  test("lists existing canvases on load", async ({ page }) => {
    // Create a canvas first via the API directly
    const res = await page.request.post("http://localhost:8000/api/canvases", {
      data: { name: "E2E Test Canvas" },
    });
    expect(res.ok()).toBeTruthy();

    await page.goto("/");
    // Scroll to top — the landing page is centered and may overflow with many canvases
    await page.evaluate(() => window.scrollTo(0, 0));
    await expect(page.getByText("E2E Test Canvas")).toBeVisible();
  });

  test("opens an existing canvas", async ({ page }) => {
    // Create a canvas and then open it from the list
    await page.request.post("http://localhost:8000/api/canvases", {
      data: { name: "Canvas To Open" },
    });

    await page.goto("/");
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.getByText("Canvas To Open").click();

    await expect(page.locator(".react-flow")).toBeVisible({ timeout: 10_000 });
  });
});
