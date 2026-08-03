import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useThemeStore } from "@/store/themeStore";

/**
 * Shared chrome for the /login and /register pages: logo, title, and the
 * ambient gradient background that matches the landing page. The form body
 * is passed in as children.
 */
export function AuthLayout({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const theme = useThemeStore((s) => s.theme);

  return (
    <div className="h-screen w-full bg-gradient-to-b from-[var(--color-base)] to-[var(--color-inset)] flex flex-col items-center justify-center px-4 noise-bg relative overflow-hidden">
      {/* Ambient background glow */}
      <div className="absolute top-1/4 left-1/3 w-[500px] h-[500px] bg-[var(--color-accent)] opacity-[0.03] rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/3 w-[400px] h-[400px] bg-[var(--color-secondary)] opacity-[0.02] rounded-full blur-[100px] pointer-events-none" />

      <div className="w-full max-w-sm relative z-10">
        {/* Logo + title */}
        <div className="flex flex-col items-center mb-8">
          <img
            src={theme === "dark" ? "/agent_graph_studio_logo_white.png" : "/agent_graph_studio_logo_dark.png"}
            alt="Logo"
            className="h-9 w-auto object-contain mb-4"
          />
          <h1 className="text-xl font-bold tracking-tight text-[var(--color-text-primary)]">
            {title}
          </h1>
          <p className="text-xs text-[var(--color-text-tertiary)] font-light mt-1">
            {subtitle}
          </p>
        </div>

        {/* Card body */}
        <div className="w-full p-6 rounded-2xl bg-gradient-to-br from-[var(--color-surface)] to-[var(--color-elevated)] border border-[var(--color-border-default)] shadow-[0_4px_20px_rgba(0,0,0,0.35),0_0_12px_rgba(255,255,255,0.02)]">
          {children}
        </div>

        {/* Footer (link to the other auth route) */}
        {footer && (
          <div className="mt-5 text-center text-xs text-[var(--color-text-tertiary)]">
            {footer}
          </div>
        )}
      </div>

      {/* Home link */}
      <Link
        to="/"
        className="absolute top-6 left-6 text-xs text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] transition-colors"
      >
        AgentGraph Studio
      </Link>
    </div>
  );
}