import {
  useEffect,
  useId,
  useRef,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

/**
 * Shared modal dialog shell.
 *
 * Rendered through a portal so it escapes the z-index context of the page
 * chrome (sidebar rail / overlay panels are z-40, landing modals z-50) and is
 * usable from any route. Maintains a module-level stack so only the topmost
 * dialog consumes Escape and Tab; a nested dialog therefore closes before its
 * parent and paints above it.
 *
 * Stack order is decided by render-time ids: React renders a parent before its
 * children but runs child effects first, so the id (not push order) decides
 * which dialog is on top and how they are stacked.
 */

const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

interface ModalHandles {
  onClose: () => void;
}

const modalHandles = new Map<number, ModalHandles>();
let nextModalId = 1;
let stackVersion = 0;
const stackListeners = new Set<() => void>();

function bumpStack() {
  stackVersion += 1;
  stackListeners.forEach((listener) => listener());
}

function subscribeToStack(listener: () => void) {
  stackListeners.add(listener);
  return () => {
    stackListeners.delete(listener);
  };
}

function getStackVersion() {
  return stackVersion;
}

/** 0 while rendering on the server / first snapshot, irrelevant client-side. */
function getServerStackVersion() {
  return 0;
}

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  /** Accessible name for the dialog; rendered as a heading. */
  title: string;
  description?: string;
  size?: "sm" | "md" | "lg" | "xl";
  children: ReactNode;
  /** Optional pinned footer (actions bar). */
  footer?: ReactNode;
  /** Set false for confirmations that must not dismiss on stray clicks. */
  closeOnBackdrop?: boolean;
}

const SIZE_CLASS: Record<NonNullable<ModalProps["size"]>, string> = {
  sm: "max-w-md",
  md: "max-w-lg",
  lg: "max-w-3xl",
  xl: "max-w-5xl",
};

export function Modal({
  open,
  onClose,
  title,
  description,
  size = "md",
  children,
  footer,
  closeOnBackdrop = true,
}: ModalProps) {
  const titleId = useId();
  const contentAreaRef = useRef<HTMLDivElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  // Assigned during render (children render after their parent), so a nested
  // modal always owns a higher id than the dialog it is rendered inside.
  const idRef = useRef<number>(-1);
  if (idRef.current === -1) {
    idRef.current = nextModalId;
    nextModalId += 1;
  }

  // Re-render whenever the modal stack changes so z-indexes stay ranked.
  useSyncExternalStore(subscribeToStack, getStackVersion, getServerStackVersion);

  // Rank within the active stack: dialogs with a lower id (opened "before"
  // this one in render order) stack below.
  const id = idRef.current;
  const stackIndex = [...modalHandles.keys()].filter((k) => k < id).length;

  useEffect(() => {
    if (!open) return;

    modalHandles.set(id, { onClose });
    bumpStack();

    previouslyFocused.current = document.activeElement as HTMLElement | null;

    // Focus the first focusable element in the content area (skipping the
    // header close button) so keyboard users land inside the dialog body.
    contentAreaRef.current
      ?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR)
      ?.focus();

    const handleKeyDown = (e: KeyboardEvent) => {
      // Only the topmost dialog reacts; lower dialogs (including the page
      // behind it) must not see this Escape/Tab.
      const highestId = Math.max(-Infinity, ...modalHandles.keys());
      if (highestId !== id) return;

      if (e.key === "Escape") {
        e.preventDefault();
        modalHandles.get(id)?.onClose();
        return;
      }

      if (e.key === "Tab" && contentAreaRef.current) {
        const items = Array.from(
          contentAreaRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
        );
        if (items.length === 0) return;
        const first = items[0];
        const last = items[items.length - 1];
        const active = document.activeElement;
        if (e.shiftKey && active === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && active === last) {
          e.preventDefault();
          first.focus();
        } else if (!items.includes(active as HTMLElement)) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      modalHandles.delete(id);
      bumpStack();
      previouslyFocused.current?.focus?.();
    };
    // onClose is intentionally excluded: the effect should not re-run (and
    // re-register the entry) just because the caller recreated the callback.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const handleBackdropMouseDown = (e: React.MouseEvent) => {
    if (closeOnBackdrop && e.target === e.currentTarget) {
      onClose();
    }
  };

  if (!open) return null;

  return createPortal(
    <div
      role="presentation"
      className="fixed inset-0 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-fade-in"
      style={{ zIndex: 60 + stackIndex * 10 }}
      onMouseDown={handleBackdropMouseDown}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`w-full ${SIZE_CLASS[size]} max-h-[85vh] flex flex-col overflow-hidden rounded-2xl bg-[var(--color-surface)] border border-[var(--color-border-strong)] shadow-2xl`}
      >
        <div className="flex items-start justify-between gap-4 px-5 pt-5 pb-3">
          <div>
            <h2
              id={titleId}
              className="text-base font-semibold text-[var(--color-text-primary)]"
            >
              {title}
            </h2>
            {description && (
              <p className="text-xs text-[var(--color-text-tertiary)] mt-0.5">
                {description}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="p-1 rounded-md text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-elevated)] transition-colors cursor-pointer shrink-0"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div ref={contentAreaRef} className="flex-1 min-h-0 overflow-y-auto px-5 pb-5">
          {children}
        </div>

        {footer && (
          <div className="px-5 py-3 border-t border-[var(--color-border-subtle)] bg-[var(--color-elevated)]">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body
  );
}