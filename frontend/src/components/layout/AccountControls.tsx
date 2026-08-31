import { useState } from "react";
import { LogOut, Settings as SettingsIcon } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import { useSettingsModalStore } from "@/store/settingsModalStore";
import { ThemeToggle } from "@/components/ThemeToggle";
import { logout as logoutApi } from "@/lib/api";

/**
 * Shared right-side account chrome used by the page top bars (Canvas TopBar
 * and the Chat page header): theme toggle + (when authenticated) the user's
 * email, a Settings button (the single entry point into the unified settings
 * dialog, opened in place — no navigation), and a Log out button. Owns the
 * logout flow so each page bar doesn't duplicate it.
 */
export function AccountControls({ themeToggleClassName = "hover:bg-[var(--color-elevated)]" }: {
  themeToggleClassName?: string;
}) {
  const user = useAuthStore((s) => s.user);
  const clearAuth = useAuthStore((s) => s.clear);
  const openSettings = useSettingsModalStore((s) => s.openSettings);
  const navigate = useNavigate();
  const [loggingOut, setLoggingOut] = useState(false);

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
    <>
      {/* Theme Toggle */}
      <ThemeToggle className={themeToggleClassName} />

      {/* Logged-in user + account + logout */}
      {user && (
        <div className="flex items-center gap-2 pl-2 ml-1 border-l border-[var(--color-border-subtle)]">
          <span className="text-[11px] text-[var(--color-text-tertiary)] truncate max-w-[140px]" title={user.email}>
            {user.email}
          </span>
          <button
            onClick={() => openSettings("account")}
            data-testid="settings-button"
            title="Settings"
            className="flex items-center justify-center p-1 rounded-md text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-elevated)] transition-all cursor-pointer"
          >
            <SettingsIcon className="w-4 h-4" />
          </button>
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
    </>
  );
}