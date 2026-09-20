import { Plus, Wrench, GitBranch } from "lucide-react";

/**
 * The landing-page hero: three primary actions styled as miniature
 * canvas nodes — colored header strip, role badge (Worker/Tool/Router),
 * and decorative handle dots top/bottom — mirroring AgentNode/ToolNode's
 * chrome instead of a generic icon-in-box card. The dot-grid backdrop
 * mirrors the real canvas background in place of blurred ambient orbs.
 * Resolved via /prototype in issue #97; see `prototype/landing-hero-graph`
 * for the discarded alternatives.
 */
export interface LandingHeroProps {
  hasCanvases: boolean;
  loading: boolean;
  onCreateCanvas: () => void;
  onImportClick: () => void;
  onChatClick: () => void;
}

export function LandingHero({ hasCanvases, loading, onCreateCanvas, onImportClick, onChatClick }: LandingHeroProps) {
  return (
    <div data-testid="landing-hero" className="relative w-full max-w-4xl mb-12">
      <div
        className="absolute inset-0 pointer-events-none opacity-60"
        style={{
          backgroundImage: "radial-gradient(circle at 1px 1px, var(--color-border-default) 1px, transparent 0)",
          backgroundSize: "24px 24px",
        }}
      />
      <div className={`grid grid-cols-1 ${hasCanvases ? "md:grid-cols-3" : "md:grid-cols-2"} gap-6 relative z-10`}>
        <button
          onClick={onCreateCanvas}
          disabled={loading}
          className="relative flex flex-col rounded-xl bg-[var(--color-surface)] border border-[var(--color-border-default)] hover:border-[var(--color-accent)] transition-all duration-200 text-left shadow-[0_4px_24px_-4px_rgba(0,0,0,0.5)] disabled:opacity-40"
        >
          <span className="absolute -top-1 left-1/2 -translate-x-1/2 w-2 h-2 rounded-full bg-[var(--color-text-tertiary)] border-2 border-[var(--color-surface)]" />
          <div className="flex items-center gap-2 px-3 py-2.5 rounded-t-xl bg-[var(--color-accent-surface)] border-b border-[var(--color-accent)]/10">
            <div className="flex items-center justify-center w-5 h-5 rounded-md bg-[var(--color-accent-subtle)]">
              <Plus className="w-3 h-3 text-[var(--color-accent)]" />
            </div>
            <span className="font-semibold text-[13px] text-[var(--color-text-primary)] flex-1">New Canvas</span>
            <span className="text-[11px] px-1.5 py-0.5 rounded-md font-semibold tracking-wide uppercase bg-[var(--color-accent-subtle)] text-[var(--color-accent)]">
              Worker
            </span>
          </div>
          <p className="px-3 py-3 text-xs text-[var(--color-text-secondary)] leading-relaxed">
            Start building a custom multi-agent system from scratch using the interactive visual node designer.
          </p>
          <span className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-2 h-2 rounded-full bg-[var(--color-accent)] border-2 border-[var(--color-surface)]" />
        </button>

        <button
          onClick={onImportClick}
          disabled={loading}
          className="relative flex flex-col rounded-xl bg-[var(--color-surface)] border border-[var(--color-border-default)] hover:border-[var(--color-info)] transition-all duration-200 text-left shadow-[0_4px_24px_-4px_rgba(0,0,0,0.5)] disabled:opacity-40"
        >
          <span className="absolute -top-1 left-1/2 -translate-x-1/2 w-2 h-2 rounded-full bg-[var(--color-text-tertiary)] border-2 border-[var(--color-surface)]" />
          <div className="flex items-center gap-2 px-3 py-2.5 rounded-t-xl bg-[var(--color-info-surface)] border-b border-[var(--color-info)]/10">
            <div className="flex items-center justify-center w-5 h-5 rounded-md bg-[var(--color-info-subtle)]">
              <Wrench className="w-3 h-3 text-[var(--color-info)]" />
            </div>
            <span className="font-semibold text-[13px] text-[var(--color-text-primary)] flex-1">Import Canvas</span>
            <span className="text-[11px] px-1.5 py-0.5 rounded-md font-semibold tracking-wide uppercase bg-[var(--color-info-subtle)] text-[var(--color-info)]">
              Tool
            </span>
          </div>
          <p className="px-3 py-3 text-xs text-[var(--color-text-secondary)] leading-relaxed">
            Upload a `.zip` archive or `.json` file containing agent configurations, custom tool code, and RAG document artifacts.
          </p>
          <span className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-2 h-2 rounded-full bg-[var(--color-info)] border-2 border-[var(--color-surface)]" />
        </button>

        {hasCanvases && (
          <button
            onClick={onChatClick}
            disabled={loading}
            className="relative flex flex-col rounded-xl bg-[var(--color-surface)] border border-[var(--color-border-default)] hover:border-[var(--color-agent)] transition-all duration-200 text-left shadow-[0_4px_24px_-4px_rgba(0,0,0,0.5)] disabled:opacity-40"
          >
            <span className="absolute -top-1 left-1/2 -translate-x-1/2 w-2 h-2 rounded-full bg-[var(--color-text-tertiary)] border-2 border-[var(--color-surface)]" />
            <div className="flex items-center gap-2 px-3 py-2.5 rounded-t-xl bg-[var(--color-agent-surface)] border-b border-[var(--color-agent)]/10">
              <div className="flex items-center justify-center w-5 h-5 rounded-md bg-[var(--color-agent-subtle)]">
                <GitBranch className="w-3 h-3 text-[var(--color-agent)]" />
              </div>
              <span className="font-semibold text-[13px] text-[var(--color-text-primary)] flex-1">Agent Chat</span>
              <span className="text-[11px] px-1.5 py-0.5 rounded-md font-semibold tracking-wide uppercase bg-[var(--color-agent-subtle)] text-[var(--color-agent)]">
                Router
              </span>
            </div>
            <p className="px-3 py-3 text-xs text-[var(--color-text-secondary)] leading-relaxed">
              Start chatting with your agent workflow, ask questions, run tool actions, and orchestrate agent task completion.
            </p>
            <span className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-2 h-2 rounded-full bg-[var(--color-agent)] border-2 border-[var(--color-surface)]" />
          </button>
        )}
      </div>
    </div>
  );
}
