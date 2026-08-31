/**
 * E2E coverage for the unified Settings dialog: openable from any surface
 * (landing, canvas) without navigating away, section tabs, deep links
 * (/settings, /account, ?section=), and theme persistence from the
 * Appearance tab — exercised against the real backend.
 *
 * The suite-wide `use.storageState` (see playwright.config.ts) starts every
 * test authenticated.
 */
import { test, expect } from "@playwright/test";

test.describe("Settings dialog — landing page", () => {
  test("opens from the landing header gear without navigating away", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("button", { name: "New Canvas" })).toBeVisible({
      timeout: 10_000,
    });

    await page.getByTestId("settings-button").click();

    // The URL is mirrored with the section param, but the landing page stays
    // mounted behind the dialog.
    await expect(page).toHaveURL(/section=account/);
    await expect(page.getByRole("dialog", { name: "Settings" })).toBeVisible();
    await expect(page.getByRole("button", { name: "New Canvas" })).toBeVisible();
  });

  test("switches tabs and loads provider settings without leaving the page", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("settings-button").click();

    await page.getByRole("tab", { name: "Providers" }).click();

    await expect(page.getByLabel("Base URL")).toBeVisible();
    await expect(page).toHaveURL(/section=providers/);
  });

  test("deep links /settings to the Providers tab and /account to the Account tab", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("dialog", { name: "Settings" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Providers" })).toHaveAttribute(
      "aria-selected",
      "true"
    );
    await expect(page.getByLabel("Base URL")).toBeVisible();

    await page.goto("/account");
    await expect(page.getByRole("dialog", { name: "Settings" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Account" })).toHaveAttribute(
      "aria-selected",
      "true"
    );
    await expect(page.getByLabel("Current password")).toBeVisible();
  });

  test("Escape closes the dialog and the section param is removed", async ({ page }) => {
    await page.goto("/?section=providers");
    await expect(page.getByRole("dialog", { name: "Settings" })).toBeVisible();

    await page.keyboard.press("Escape");

    await expect(page.getByRole("dialog", { name: "Settings" })).not.toBeVisible();
    await expect(page).not.toHaveURL(/section=/);
  });

  test("keeps theme changes made in the Appearance tab", async ({ page }) => {
    await page.goto("/?section=appearance");
    await expect(page.getByRole("dialog", { name: "Settings" })).toBeVisible();

    await page.getByRole("radio", { name: "Light" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");

    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", { name: "Settings" })).not.toBeVisible();

    // Reload proves the choice persisted (localStorage).
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  });
});

test.describe("Settings dialog — canvas", () => {
  test("opens over the canvas editor, preserves canvas state, and Escape returns", async ({ page }) => {
    // A canvas is created per test (matching canvas.spec.ts's self-contained
    // pattern); the gear in the canvas TopBar must open the dialog in place.
    await page.goto("/");
    await page.getByRole("button", { name: "New Canvas" }).click();
    await expect(page.getByTestId("top-bar")).toBeVisible({ timeout: 10_000 });

    await page.getByTestId("settings-button").click();
    await expect(page.getByRole("dialog", { name: "Settings" })).toBeVisible();
    // The canvas chrome and rail survive underneath the overlay.
    await expect(page.getByTestId("top-bar")).toBeVisible();
    await expect(page.getByTestId("sidebar-rail")).toBeAttached();

    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", { name: "Settings" })).not.toBeVisible();
    await expect(page.getByTestId("top-bar")).toBeVisible();
  });

  test("is reachable from the sidebar rail without navigating", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "New Canvas" }).click();
    await expect(page.getByTestId("top-bar")).toBeVisible({ timeout: 10_000 });

    await page.getByTestId("settings-rail-button").click();

    await expect(page.getByRole("dialog", { name: "Settings" })).toBeVisible();
    // Still on the canvas route — the rail button is an in-place trigger.
    await expect(page).toHaveURL(/\/canvas\//);
    await expect(page.getByTestId("top-bar")).toBeVisible();
  });
});