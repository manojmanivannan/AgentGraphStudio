import { useState } from "react";
import { Check, Loader2, AlertCircle, Home, LogOut } from "lucide-react";
import { useCanvasStore } from "@/store/canvasStore";
import { useAuthStore } from "@/store/authStore";
import { useNavigate } from "react-router-dom";
import { ThemeToggle } from "@/components/ThemeToggle";
import { logout as logoutApi } from "@/lib/api";

export function TopBar() {
  const canvasId = useCanvasStore((s) => s.canvasId);
  const canvasName = useCanvasStore((s) => s.canvasName);
  const setName = useCanvasStore((s) => s.setName);
  const saveStatus = useCanvasStore((s) => s.saveStatus);
  const selectedNodeId = useCanvasStore((s) => s.selectedNodeId);
  const propertiesWidth = useCanvasStore((s) => s.propertiesWidth);
  const isDraggingPanel = useCanvasStore((s) => s.isDraggingPanel);
  const sidebarCollapsed = useCanvasStore((s) => s.sidebarCollapsed);
  const user = useAuthStore((s) => s.user);
  const clearAuth = useAuthStore((s) => s.clear);

  const navigate = useNavigate();
  const [loggingOut, setLoggingOut] = useState(false);

  const propertiesOpen = selectedNodeId !== null;

  const leftOffset = sidebarCollapsed ? 64 : 256;

  // Shift right edge to avoid being covered by overlay panels
  const rightOffset = propertiesOpen ? propertiesWidth : 0;

  const handleLogout = async () => {
    setLoggingOut(true);
    try {
      await logoutApi();
    } catch (err) {
      // Even if the backend call fails (network down, server error), clear the
      // local session and return to /login — the cookie is httpOnly so we
      // can't clear it client-side, but the user is effectively logged out of
      // this client. They'll be re-prompted on next /auth/me.
      console.error("Logout request failed:", err);
    } finally {
      clearAuth();
      setLoggingOut(false);
      navigate("/login", { replace: true });
    }
  };

  return (
    <div
      data-testid="top-bar"
      className={`absolute top-0 h-10 chrome-glass border-b border-[var(--color-border-subtle)] flex items-center px-4 gap-3 z-30 ${
        isDraggingPanel ? "" : "transition-all duration-300 ease-out"
      }`}
      style={{ left: leftOffset, right: rightOffset }}
    >
      {/* Home button */}
      <button
        onClick={() => {
          useCanvasStore.getState().reset();
          navigate("/");
        }}
        data-testid="home-button"
        className="flex items-center justify-center p-1 rounded-md text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-elevated)] transition-all"
        title="Back to Landing Page"
      >
        <Home className="w-4 h-4" />
      </button>

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

      {/* Theme Toggle */}
      <ThemeToggle className="hover:bg-[var(--color-elevated)]" />

      {/* Logged-in user + logout */}
      {user && (
        <div className="flex items-center gap-2 pl-2 ml-1 border-l border-[var(--color-border-subtle)]">
          <span className="text-[11px] text-[var(--color-text-tertiary)] truncate max-w-[140px]" title={user.email}>
            {user.email}
          </span>
          <button
            onClick={handleLogout}
            disabled={loggingOut}
            data-testid="logout-button"
            title="Log out"
            className="flex items-center justify-center p-1 rounded-md text-[var(--color-text-tertiary)] hover:text-[var(--color-danger)] hover:bg-[var(--color-elevated)] transition-all disabled:opacity-50 cursor-pointer"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  );
}