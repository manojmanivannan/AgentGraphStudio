import { describe, it, expect, beforeEach } from "vitest";
import { useUnsavedChangesPromptStore, promptUnsavedChanges } from "@/store/unsavedChangesPromptStore";

beforeEach(() => {
  useUnsavedChangesPromptStore.setState({ pending: null });
});

describe("unsavedChangesPromptStore", () => {
  it("starts with no pending prompt", () => {
    expect(useUnsavedChangesPromptStore.getState().pending).toBeNull();
  });

  it("request() registers a pending prompt", () => {
    void useUnsavedChangesPromptStore.getState().request();
    expect(useUnsavedChangesPromptStore.getState().pending).not.toBeNull();
  });

  it("settle('save') resolves the pending promise with 'save' and clears it", async () => {
    const promise = useUnsavedChangesPromptStore.getState().request();
    useUnsavedChangesPromptStore.getState().settle("save");
    await expect(promise).resolves.toBe("save");
    expect(useUnsavedChangesPromptStore.getState().pending).toBeNull();
  });

  it("settle('discard') resolves the pending promise with 'discard'", async () => {
    const promise = useUnsavedChangesPromptStore.getState().request();
    useUnsavedChangesPromptStore.getState().settle("discard");
    await expect(promise).resolves.toBe("discard");
  });

  it("settle('cancel') resolves the pending promise with 'cancel'", async () => {
    const promise = useUnsavedChangesPromptStore.getState().request();
    useUnsavedChangesPromptStore.getState().settle("cancel");
    await expect(promise).resolves.toBe("cancel");
  });

  it("settle() with no pending prompt is a no-op", () => {
    expect(() => useUnsavedChangesPromptStore.getState().settle("cancel")).not.toThrow();
  });

  describe("promptUnsavedChanges() API", () => {
    it("resolves to the settled choice", async () => {
      const promise = promptUnsavedChanges();
      useUnsavedChangesPromptStore.getState().settle("discard");
      await expect(promise).resolves.toBe("discard");
    });
  });
});
