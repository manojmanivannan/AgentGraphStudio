/**
 * E2E tests for the ChatPanel component and execution streaming.
 * Uses canvasWithWorkflow and wsFixture.
 */
import { test, expect } from "./fixtures";

test.beforeEach(async ({ page, canvasWithWorkflow }) => {
  await page.getByTestId("chat-toggle").click();
});

test.describe("Chat Panel — conversation management", () => {
  test("shows 'No Chat Active' placeholder when no conversation is active", async ({
    page,
    canvasWithWorkflow,
  }) => {
    // Navigate directly to the empty chat page for this canvas
    await page.goto(`/chat/empty?canvas=${canvasWithWorkflow.canvasId}`);
    await expect(page.getByText("No Chat Active")).toBeVisible();
    await expect(page.getByText("Start New Conversation")).toBeVisible();
  });

  test("shows sidebar with Recent Chats and New Conversation button", async ({
    page,
    canvasWithWorkflow: _,
  }) => {
    await expect(page.getByText("Recent Chats")).toBeVisible();
    await expect(page.getByRole("button", { name: "New Conversation" })).toBeVisible();
  });

  test("clicking New Conversation creates a conversation and shows it selected", async ({
    page,
    canvasWithWorkflow: _,
  }) => {
    await page.getByRole("button", { name: "New Conversation" }).click();

    // The main heading should show the active conversation name
    await expect(page.getByText("Chat session")).toBeVisible();
    await expect(page.getByText("New Conversation").first()).toBeVisible();
  });

  test("deleting a conversation removes it from the list", async ({
    page,
    canvasWithWorkflow: _,
  }) => {
    // There is already a conversation created by the chat-toggle click in beforeEach.
    // Hover the conversation list item and click the delete button
    const item = page.locator("aside").getByText("New Conversation").first();
    await item.hover();
    
    // Find the delete button in the hovered item and click it
    await page.getByTitle("Delete conversation").first().click();

    // Click confirm Delete button in modal (use exact match to avoid strictness violation)
    await page.getByRole("button", { name: "Delete", exact: true }).click();

    // It should navigate to /chat/empty and show the placeholder
    await expect(page.getByText("No Chat Active")).toBeVisible({ timeout: 5000 });
  });
});

test.describe("Chat Panel — message sending and streaming", () => {
  test("user message appears immediately after sending", async ({
    page,
    canvasWithWorkflow: _,
  }) => {
    await page.getByTestId("chat-input").fill("Hello agent");
    await page.getByTestId("chat-input").press("Enter");

    await expect(page.getByText("Hello agent")).toBeVisible({ timeout: 5000 });
  });

  test("loading indicator appears while running and stop button is visible", async ({
    page,
    canvasWithWorkflow: _,
  }) => {
    await page.getByTestId("chat-input").fill("Run test");
    await page.getByTestId("chat-input").press("Enter");

    // Loading dots and stop button should appear
    await expect(page.getByTestId("stop-button")).toBeVisible({ timeout: 5000 });
  });
});

test.describe("Chat Panel — stop button", () => {
  test("stop button closes the WebSocket and UI returns to idle", async ({
    page,
    canvasWithWorkflow: _,
  }) => {
    await page.getByTestId("chat-input").fill("Long run");
    await page.getByTestId("chat-input").press("Enter");

    // Wait for WebSocket to be running
    await expect(page.getByTestId("stop-button")).toBeVisible({ timeout: 5000 });

    // Click stop
    await page.getByTestId("stop-button").click();

    // UI returns to idle
    await expect(page.getByTestId("send-button")).toBeVisible({ timeout: 5000 });
  });
});
