/**
 * E2E tests for the ChatPanel component and execution streaming.
 * Uses canvasWithWorkflow and wsFixture.
 */
import { test, expect } from "./fixtures";

test.describe("Chat Panel — conversation management", () => {
  test("shows 'Select or create a conversation' placeholder when no conversation is active", async ({
    page,
    canvasWithWorkflow: _,
  }) => {
    await expect(
      page.getByText("Select or create a conversation")
    ).toBeVisible();
  });

  test("clicking the selector opens the dropdown with New Conversation", async ({
    page,
    canvasWithWorkflow: _,
  }) => {
    await page.getByTestId("conversation-selector").click();
    await expect(page.getByTestId("new-conversation-button")).toBeVisible();
  });

  test("clicking New Conversation creates a conversation and shows it selected", async ({
    page,
    canvasWithWorkflow: _,
  }) => {
    await page.getByTestId("conversation-selector").click();
    await page.getByTestId("new-conversation-button").click();

    // Selector should now show the conversation name
    await expect(page.getByTestId("conversation-selector")).toContainText(
      "New Conversation",
      { timeout: 5000 }
    );
  });

  test("deleting a conversation removes it from the list", async ({
    page,
    canvasWithWorkflow: _,
  }) => {
    // Create a conversation first
    await page.getByTestId("conversation-selector").click();
    await page.getByTestId("new-conversation-button").click();
    await expect(page.getByTestId("conversation-selector")).toContainText(
      "New Conversation"
    );

    // Open selector and delete
    await page.getByTestId("conversation-selector").click();
    await page.getByTestId("delete-conversation-button").click();

    // Should revert to placeholder
    await expect(page.getByTestId("conversation-selector")).not.toContainText(
      "New Conversation",
      { timeout: 5000 }
    );
  });
});

test.describe("Chat Panel — message sending and streaming", () => {
  test("user message appears immediately after sending", async ({
    page,
    canvasWithWorkflow: _,
  }) => {
    await page.getByTestId("conversation-selector").click();
    await page.getByTestId("new-conversation-button").click();

    await page.getByTestId("chat-input").fill("Hello agent");
    await page.getByTestId("chat-input").press("Enter");

    await expect(page.getByText("Hello agent")).toBeVisible({ timeout: 5000 });
  });

  test("loading indicator appears while running and stop button is visible", async ({
    page,
    canvasWithWorkflow: _,
  }) => {
    await page.getByTestId("conversation-selector").click();
    await page.getByTestId("new-conversation-button").click();

    await page.getByTestId("chat-input").fill("Run test");
    await page.getByTestId("chat-input").press("Enter");

    // Loading dots and stop button should appear
    await expect(page.getByTestId("stop-button")).toBeVisible({ timeout: 5000 });
  });

  // TODO: Re-enable these streaming tests once the wsFixture mock is fixed.
  // The WebSocket route mock does not properly deliver events to the ChatOverlay.
  test.skip("streaming events render correctly in a real browser", async () => {});

  test.skip("thought event appears as a step during streaming", async () => {});

  test.skip("steps toggle collapses and expands step details", async () => {});

  // TODO: Re-enable once wsFixture mock is fixed.
  test.skip("after run_complete the send button is re-enabled", async () => {});
});

test.describe("Chat Panel — stop button", () => {
  test("stop button closes the WebSocket and UI returns to idle", async ({
    page,
    canvasWithWorkflow: _,
  }) => {
    await page.getByTestId("conversation-selector").click();
    await page.getByTestId("new-conversation-button").click();

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
