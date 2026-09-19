import { useEffect } from "react";
import { createPortal } from "react-dom";
import { CheckCircle2, AlertCircle, Info, X } from "lucide-react";
import { useToastStore, type ToastEntry, type ToastVariant } from "@/store/toastStore";

const AUTO_DISMISS_MS = 5000;

const VARIANT_STYLE: Record<ToastVariant, { icon: typeof Info; className: string }> = {
  success: {
    icon: CheckCircle2,
    className: "border-[var(--color-accent)]/40 text-[var(--color-accent)]",
  },
  error: {
    icon: AlertCircle,
    className: "border-[var(--color-danger)]/40 text-[var(--color-danger)]",
  },
  info: {
    icon: Info,
    className: "border-[var(--color-border-strong)] text-[var(--color-text-primary)]",
  },
};

function ToastItem({ entry }: { entry: ToastEntry }) {
  const dismiss = useToastStore((s) => s.dismiss);

  useEffect(() => {
    const timer = setTimeout(() => dismiss(entry.id), AUTO_DISMISS_MS);
    return () => clearTimeout(timer);
  }, [entry.id, dismiss]);

  const { icon: Icon, className } = VARIANT_STYLE[entry.variant];

  return (
    <div
      role="status"
      className={`flex items-start gap-2.5 px-4 py-3 rounded-xl border bg-[var(--color-surface)] shadow-2xl min-w-[260px] max-w-sm animate-fade-in ${className}`}
    >
      <Icon className="w-4 h-4 mt-0.5 shrink-0" />
      <p className="text-[12px] text-[var(--color-text-secondary)] flex-1">{entry.message}</p>
      <button
        type="button"
        onClick={() => dismiss(entry.id)}
        aria-label="Dismiss notification"
        className="p-0.5 rounded text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] transition-colors cursor-pointer shrink-0"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

/**
 * Mounted once near the app root. Renders notices dispatched via the
 * `toast` API (`@/store/toastStore`) — the in-app replacement for native
 * `alert()` — stacked bottom-right, auto-dismissing after 5s.
 */
export function ToastHost() {
  const toasts = useToastStore((s) => s.toasts);

  if (toasts.length === 0 || typeof document === "undefined") return null;

  return createPortal(
    <div className="fixed bottom-4 right-4 z-[70] flex flex-col gap-2 pointer-events-none">
      {toasts.map((t) => (
        <div key={t.id} className="pointer-events-auto">
          <ToastItem entry={t} />
        </div>
      ))}
    </div>,
    document.body
  );
}
