import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AlertCircle, Loader2 } from "lucide-react";
import { AuthLayout } from "./AuthLayout";
import { login } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

export default function LoginPage() {
  const navigate = useNavigate();
  const setUser = useAuthStore((s) => s.setUser);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const user = await login(email, password);
      setUser(user);
      navigate("/");
    } catch (err: any) {
      setError(err?.message || "Failed to log in.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthLayout
      title="Welcome back"
      subtitle="Log in to your AgentGraph Studio account"
      footer={
        <>
          Don&apos;t have an account?{" "}
          <Link
            to="/register"
            className="text-[var(--color-accent)] hover:opacity-80 font-medium"
          >
            Register
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        {error && (
          <div
            role="alert"
            className="flex items-start gap-2 p-3 rounded-lg bg-[var(--color-danger-subtle)] border border-[var(--color-danger)]/30 text-[var(--color-danger)]"
          >
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <p className="text-xs">{error}</p>
          </div>
        )}

        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-[var(--color-text-secondary)]">
            Email
          </span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
            className="px-3 py-2 bg-[var(--color-inset)] border border-[var(--color-border-default)] rounded-lg text-sm outline-none focus:border-[var(--color-accent)] transition-colors text-[var(--color-text-primary)] placeholder-[var(--color-text-tertiary)]"
            placeholder="you@example.com"
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-[var(--color-text-secondary)]">
            Password
          </span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
            className="px-3 py-2 bg-[var(--color-inset)] border border-[var(--color-border-default)] rounded-lg text-sm outline-none focus:border-[var(--color-accent)] transition-colors text-[var(--color-text-primary)] placeholder-[var(--color-text-tertiary)]"
            placeholder="••••••••"
          />
        </label>

        <button
          type="submit"
          disabled={submitting}
          className="btn-primary bg-[var(--color-accent)] hover:bg-[var(--color-accent)] text-white text-sm px-4 py-2 rounded-lg font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 cursor-pointer"
        >
          {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
          {submitting ? "Logging in…" : "Log in"}
        </button>
      </form>
    </AuthLayout>
  );
}