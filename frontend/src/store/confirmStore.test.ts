import { describe, it, expect, beforeEach } from "vitest";
import { useConfirmStore, confirm } from "@/store/confirmStore";

beforeEach(() => {
  useConfirmStore.setState({ pending: null });
});

describe("confirmStore", () => {
  it("starts with no pending confirmation", () => {
    expect(useConfirmStore.getState().pending).toBeNull();
  });

  it("request() registers a pending confirmation with the given options", () => {
    void useConfirmStore.getState().request({ title: "Delete document", description: "Sure?" });
    expect(useConfirmStore.getState().pending).toMatchObject({
      title: "Delete document",
      description: "Sure?",
    });
  });

  it("settle(true) resolves the pending promise with true and clears it", async () => {
    const promise = useConfirmStore.getState().request({ title: "Delete document" });
    useConfirmStore.getState().settle(true);
    await expect(promise).resolves.toBe(true);
    expect(useConfirmStore.getState().pending).toBeNull();
  });

  it("settle(false) resolves the pending promise with false", async () => {
    const promise = useConfirmStore.getState().request({ title: "Delete document" });
    useConfirmStore.getState().settle(false);
    await expect(promise).resolves.toBe(false);
  });

  it("settle() with no pending confirmation is a no-op", () => {
    expect(() => useConfirmStore.getState().settle(true)).not.toThrow();
  });

  describe("confirm() API", () => {
    it("resolves to true once settled with true", async () => {
      const promise = confirm({ title: "Delete document", danger: true });
      useConfirmStore.getState().settle(true);
      await expect(promise).resolves.toBe(true);
    });
  });
});
