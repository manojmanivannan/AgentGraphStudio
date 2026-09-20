import { useCanvasStore } from "@/store/canvasStore";
import { saveCanvasNow } from "@/hooks/useCanvasPersistence";
import { promptUnsavedChanges } from "@/store/unsavedChangesPromptStore";

/**
 * Guards in-app navigation away from the Visual Canvas editor.
 *
 * Runs `navigateAway` immediately when the canvas has no unsaved changes.
 * Otherwise prompts the user to save, discard, or cancel first: "save" saves
 * the canvas and only navigates if the save succeeds (leaving the user on
 * the page with the "Save failed" indicator otherwise), "discard" navigates
 * without saving, and "cancel" (including dismissing the dialog) leaves the
 * user on the current page.
 */
export async function guardUnsavedNavigation(
  navigateAway: () => void | Promise<void>
): Promise<void> {
  if (!useCanvasStore.getState().isDirty) {
    await navigateAway();
    return;
  }

  const choice = await promptUnsavedChanges();
  if (choice === "cancel") return;

  if (choice === "save") {
    const saved = await saveCanvasNow();
    if (!saved) return;
  }

  await navigateAway();
}
