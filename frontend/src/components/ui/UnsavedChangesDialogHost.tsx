import { Modal } from "@/components/ui/Modal";
import { useUnsavedChangesPromptStore } from "@/store/unsavedChangesPromptStore";

/**
 * Mounted once near the app root (see `AppShell`). Renders the 3-way
 * save/discard/cancel prompt requested via `promptUnsavedChanges()`
 * (`@/store/unsavedChangesPromptStore`) whenever the user tries to navigate
 * away from a canvas that has unsaved changes.
 */
export function UnsavedChangesDialogHost() {
  const pending = useUnsavedChangesPromptStore((s) => s.pending);
  const settle = useUnsavedChangesPromptStore((s) => s.settle);

  return (
    <Modal
      open={pending !== null}
      onClose={() => settle("cancel")}
      title="Unsaved changes"
      description="This canvas has unsaved changes. Save them before leaving, discard them, or stay on this page."
      size="sm"
      footer={
        <div className="flex justify-end gap-2">
          <button type="button" onClick={() => settle("cancel")} className="btn-ghost">
            Cancel
          </button>
          <button
            type="button"
            onClick={() => settle("discard")}
            data-testid="unsaved-changes-discard"
            className="btn-danger-ghost"
          >
            Discard changes
          </button>
          <button
            type="button"
            onClick={() => settle("save")}
            data-testid="unsaved-changes-save"
            className="btn-primary"
          >
            Save & continue
          </button>
        </div>
      }
    >
      <div />
    </Modal>
  );
}
