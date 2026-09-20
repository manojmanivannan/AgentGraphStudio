import { describe, it, expect, beforeEach, vi } from "vitest";
import { useCanvasStore } from "@/store/canvasStore";
import { useUnsavedChangesPromptStore } from "@/store/unsavedChangesPromptStore";

const saveCanvasNowMock = vi.fn();

vi.mock("@/hooks/useCanvasPersistence", () => ({
  saveCanvasNow: () => saveCanvasNowMock(),
}));

// Imported after the mock so the guard picks up the mocked saveCanvasNow.
const { guardUnsavedNavigation } = await import("@/lib/unsavedChangesGuard");

beforeEach(() => {
  useCanvasStore.getState().reset();
  useUnsavedChangesPromptStore.setState({ pending: null });
  saveCanvasNowMock.mockReset();
});

describe("guardUnsavedNavigation", () => {
  it("navigates immediately when there are no unsaved changes", async () => {
    const navigateAway = vi.fn();

    await guardUnsavedNavigation(navigateAway);

    expect(navigateAway).toHaveBeenCalledTimes(1);
    expect(saveCanvasNowMock).not.toHaveBeenCalled();
  });

  it("prompts and navigates after 'discard' without saving", async () => {
    useCanvasStore.getState().setIsDirty(true);
    const navigateAway = vi.fn();

    const guardPromise = guardUnsavedNavigation(navigateAway);
    await vi.waitFor(() => expect(useUnsavedChangesPromptStore.getState().pending).not.toBeNull());
    useUnsavedChangesPromptStore.getState().settle("discard");
    await guardPromise;

    expect(navigateAway).toHaveBeenCalledTimes(1);
    expect(saveCanvasNowMock).not.toHaveBeenCalled();
  });

  it("does not navigate when 'cancel' is chosen", async () => {
    useCanvasStore.getState().setIsDirty(true);
    const navigateAway = vi.fn();

    const guardPromise = guardUnsavedNavigation(navigateAway);
    await vi.waitFor(() => expect(useUnsavedChangesPromptStore.getState().pending).not.toBeNull());
    useUnsavedChangesPromptStore.getState().settle("cancel");
    await guardPromise;

    expect(navigateAway).not.toHaveBeenCalled();
  });

  it("saves then navigates when 'save' is chosen and the save succeeds", async () => {
    useCanvasStore.getState().setIsDirty(true);
    saveCanvasNowMock.mockResolvedValue(true);
    const navigateAway = vi.fn();

    const guardPromise = guardUnsavedNavigation(navigateAway);
    await vi.waitFor(() => expect(useUnsavedChangesPromptStore.getState().pending).not.toBeNull());
    useUnsavedChangesPromptStore.getState().settle("save");
    await guardPromise;

    expect(saveCanvasNowMock).toHaveBeenCalledTimes(1);
    expect(navigateAway).toHaveBeenCalledTimes(1);
  });

  it("does not navigate when 'save' is chosen but the save fails", async () => {
    useCanvasStore.getState().setIsDirty(true);
    saveCanvasNowMock.mockResolvedValue(false);
    const navigateAway = vi.fn();

    const guardPromise = guardUnsavedNavigation(navigateAway);
    await vi.waitFor(() => expect(useUnsavedChangesPromptStore.getState().pending).not.toBeNull());
    useUnsavedChangesPromptStore.getState().settle("save");
    await guardPromise;

    expect(saveCanvasNowMock).toHaveBeenCalledTimes(1);
    expect(navigateAway).not.toHaveBeenCalled();
  });
});
