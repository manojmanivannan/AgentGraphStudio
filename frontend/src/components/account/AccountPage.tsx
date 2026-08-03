import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, Check, Loader2, MonitorSmartphone } from "lucide-react";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { changePassword, logoutOtherSessions } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

type Feedback =
  | { kind: "success"; message: string }
  | { kind: "error"; message: string }
  | null;

export default function AccountPage() {
  const user = useAuthStore((s) => s.user);

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [pwFeedback, setPwFeedback] = useState<Feedback>(null);
  const [changing, setChanging] = useState(false);

  const [logoutFeedback, setLogoutFeedback] = useState<Feedback>(null);
  const [loggingOut, setLoggingOut] = useState(false);

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPwFeedback(null);
    if (next !== confirm) {
      setPwFeedback({ kind: "error", message: "Passwords do not match." });
      return;
    }
    setChanging(true);
    try {
      await changePassword(current, next);
      setPwFeedback({ kind: "success", message: "Password changed. Other devices were signed out." });
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (err: any) {
      setPwFeedback({ kind: "error", message: err?.message || "Failed to change password." });
    } finally {
      setChanging(false);
    }
  };

  const handleLogoutOthers = async () => {
    setLogoutFeedback(null);
    setLoggingOut(true);
    try {
      const { revoked } = await logoutOtherSessions();
      setLogoutFeedback({
        kind: "success",
        message: `Signed out ${revoked} other session${revoked === 1 ? "" : "s"}.`,
      });
    } catch (err: any) {
      setLogoutFeedback({ kind: "error", message: err?.message || "Failed to log out other sessions." });
    } finally {
      setLoggingOut(false);
    }
  };

  return (
    <AuthLayout
      title="Account"
      subtitle="Manage your password and active sessions"
      footer={
        <Link to="/" className="text-[var(--color-accent)] hover:opacity-80 font-medium">
          Back to AgentGraph Studio
        </Link>
      }
    >
      {/* Current user */}
      <div className="mb-6 pb-4 border-b border-[var(--color-border-subtle)]">
        <p className="text-[10px] uppercase tracking-wider text-[var(--color-text-tertiary)] font-medium">
          Signed in as
        </p>
        <p className="text-sm text-[var(--color-text-primary)] font-medium truncate" title={user?.email ?? ""}>
          {user?.email ?? "—"}
        </p>
      </div>

      {/* Change password */}
      <form onSubmit={handleChangePassword} className="flex flex-col gap-4 mb-6">
        <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">Change password</h2>

        {pwFeedback && (
          <div
            role="alert"
            className={`flex items-start gap-2 p-3 rounded-lg border text-xs ${
              pwFeedback.kind === "success"
                ? "bg-[var(--color-success-subtle)] border-[var(--color-success)]/30 text-[var(--color-success)]"
                : "bg-[var(--color-danger-subtle)] border-[var(--color-danger)]/30 text-[var(--color-danger)]"
            }`}
          >
            {pwFeedback.kind === "success" ? (
              <Check className="w-4 h-4 shrink-0 mt-0.5" />
            ) : (
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            )}
            <p>{pwFeedback.message}</p>
          </div>
        )}

        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-[var(--color-text-secondary)]">Current password</span>
          <input
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            required
            autoComplete="current-password"
            className="px-3 py-2 bg-[var(--color-inset)] border border-[var(--color-border-default)] rounded-lg text-sm outline-none focus:border-[var(--color-accent)] transition-colors text-[var(--color-text-primary)] placeholder-[var(--color-text-tertiary)]"
            placeholder="••••••••"
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-[var(--color-text-secondary)]">New password</span>
          <input
            type="password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            required
            autoComplete="new-password"
            className="px-3 py-2 bg-[var(--color-inset)] border border-[var(--color-border-default)] rounded-lg text-sm outline-none focus:border-[var(--color-accent)] transition-colors text-[var(--color-text-primary)] placeholder-[var(--color-text-tertiary)]"
            placeholder="••••••••"
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-[var(--color-text-secondary)]">Confirm new password</span>
          <input
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            autoComplete="new-password"
            className="px-3 py-2 bg-[var(--color-inset)] border border-[var(--color-border-default)] rounded-lg text-sm outline-none focus:border-[var(--color-accent)] transition-colors text-[var(--color-text-primary)] placeholder-[var(--color-text-tertiary)]"
            placeholder="••••••••"
          />
        </label>

        <button
          type="submit"
          disabled={changing}
          className="btn-primary bg-[var(--color-accent)] hover:bg-[var(--color-accent)] text-white text-sm px-4 py-2 rounded-lg font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 cursor-pointer"
        >
          {changing && <Loader2 className="w-4 h-4 animate-spin" />}
          {changing ? "Changing…" : "Change password"}
        </button>
      </form>

      {/* Logout other sessions */}
      <div className="pt-4 border-t border-[var(--color-border-subtle)]">
        <div className="flex items-center gap-2 mb-2">
          <MonitorSmartphone className="w-4 h-4 text-[var(--color-text-tertiary)]" />
          <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">Active sessions</h2>
        </div>
        <p className="text-xs text-[var(--color-text-tertiary)] mb-3">
          Sign out every other device without ending this session.
        </p>

        {logoutFeedback && (
          <div
            role="alert"
            className={`flex items-start gap-2 p-3 mb-3 rounded-lg border text-xs ${
              logoutFeedback.kind === "success"
                ? "bg-[var(--color-success-subtle)] border-[var(--color-success)]/30 text-[var(--color-success)]"
                : "bg-[var(--color-danger-subtle)] border-[var(--color-danger)]/30 text-[var(--color-danger)]"
            }`}
          >
            {logoutFeedback.kind === "success" ? (
              <Check className="w-4 h-4 shrink-0 mt-0.5" />
            ) : (
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            )}
            <p>{logoutFeedback.message}</p>
          </div>
        )}

        <button
          type="button"
          onClick={handleLogoutOthers}
          disabled={loggingOut}
          className="w-full text-sm px-4 py-2 rounded-lg font-medium border border-[var(--color-border-default)] text-[var(--color-text-primary)] hover:bg-[var(--color-elevated)] disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 cursor-pointer transition-colors"
        >
          {loggingOut && <Loader2 className="w-4 h-4 animate-spin" />}
          {loggingOut ? "Signing out…" : "Log out other sessions"}
        </button>
      </div>
    </AuthLayout>
  );
}