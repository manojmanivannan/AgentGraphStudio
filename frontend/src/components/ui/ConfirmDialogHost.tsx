import { Modal } from "@/components/ui/Modal";
import { useConfirmStore } from "@/store/confirmStore";

/**
 * Mounted once near the app root. Renders the `Modal`-based confirmation
 * requested via the `confirm()` API (`@/store/confirmStore`) — the in-app
 * replacement for native `confirm()`.
 */
export function ConfirmDialogHost() {
  const pending = useConfirmStore((s) => s.pending);
  const settle = useConfirmStore((s) => s.settle);

  return (
    <Modal
      open={pending !== null}
      onClose={() => settle(false)}
      title={pending?.title ?? ""}
      description={pending?.description}
      size="sm"
      footer={
        <div className="flex justify-end gap-2">
          <button type="button" onClick={() => settle(false)} className="btn-secondary">
            {pending?.cancelLabel ?? "Cancel"}
          </button>
          <button
            type="button"
            onClick={() => settle(true)}
            data-testid="confirm-dialog-confirm"
            className={pending?.danger ? "btn-danger" : "btn-primary"}
          >
            {pending?.confirmLabel ?? "Confirm"}
          </button>
        </div>
      }
    >
      <div />
    </Modal>
  );
}
