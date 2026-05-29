import { Check, Loader2, AlertCircle, MessageSquare, Activity, Layout } from "lucide-react";
import { useCanvasStore } from "@/store/canvasStore";

export function TopBar() {
  const canvasName = useCanvasStore((s) => s.canvasName);
  const setName = useCanvasStore((s) => s.setName);
  const saveStatus = useCanvasStore((s) => s.saveStatus);
  const chatOpen = useCanvasStore((s) => s.chatOpen);
  const toggleChat = useCanvasStore((s) => s.toggleChat);
  const observabilityOpen = useCanvasStore((s) => s.observabilityOpen);
  const toggleObservability = useCanvasStore((s) => s.toggleObservability);

  // When observability is open, the sidebar rail is hidden so left offset resets to 0
  const leftOffset = observabilityOpen ? "left-0" : "left-12";

  return (
    <div
      data-testid="top-bar"
      className={`absolute top-0 ${leftOffset} right-0 h-10 chrome-glass border-b border-[var(--color-border-subtle)] flex items-center px-4 gap-3 z-30`}
    >
      {/* Canvas name */}
      <input
        type="text"
        value={canvasName}
        onChange={(e) => setName(e.target.value)}
        data-testid="canvas-name-input"
        className="text-[14px] font-semibold text-[var(--color-text-primary)] bg-transparent border-b border-transparent hover:border-[var(--color-border-default)] focus:border-[var(--color-accent)] focus:outline-none px-1 py-0.5 w-52 placeholder:text-[var(--color-text-tertiary)] transition-colors tracking-[-0.01em]"
        placeholder="Canvas name"
      />

      <div className="flex-1" />

      {/* Save status indicator */}
      <div
        className="flex items-center gap-1.5 text-[11px] text-[var(--color-text-tertiary)]"
        data-testid="save-status"
      >
        {saveStatus === "saving" && (
          <>
            <Loader2 className="w-3 h-3 save-indicator-saving" />
            <span>Saving…</span>
          </>
        )}
        {saveStatus === "saved" && (
          <>
            <Check className="w-3 h-3 text-[var(--color-success)]" />
            <span className="text-[var(--color-success)]">Saved</span>
          </>
        )}
        {saveStatus === "error" && (
          <>
            <AlertCircle className="w-3 h-3 text-[var(--color-danger)]" />
            <span className="text-[var(--color-danger)]">Save failed</span>
          </>
        )}
      </div>

      {/* Back to Canvas button - only show when in observability mode */}
      {observabilityOpen && (
        <button
          onClick={toggleObservability}
          data-testid="back-to-canvas"
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[12px] font-medium transition-colors text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-elevated)]"
        >
          <Layout className="w-3.5 h-3.5" />
          Canvas
        </button>
      )}

      {/* Observability toggle */}
      <button
        onClick={toggleObservability}
        data-testid="observability-toggle"
        className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[12px] font-medium transition-colors ${
          observabilityOpen
            ? "text-[var(--color-accent)] bg-[var(--color-accent-subtle)]"
            : "text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)] hover:bg-[var(--color-elevated)]"
        }`}
      >
        <Activity className="w-3.5 h-3.5" />
        Observability
      </button>

      {/* Chat toggle */}
      <button
        onClick={toggleChat}
        data-testid="chat-toggle"
        className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[12px] font-medium transition-colors ${
          chatOpen
            ? "text-[var(--color-accent)] bg-[var(--color-accent-subtle)]"
            : "text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)] hover:bg-[var(--color-elevated)]"
        }`}
      >
        <MessageSquare className="w-3.5 h-3.5" />
        Chat
      </button>
    </div>
  );
}