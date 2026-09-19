import type { RefObject } from "react";
import { Plus, Upload, MessageSquare, GitBranch, Wrench, Brain } from "lucide-react";

/**
 * PROTOTYPE ONLY — three structurally different takes on the landing-page
 * hero (ticket: "Landing page draws from the graph metaphor instead of
 * generic SaaS cards"). Switchable via `?variant=` on the `/` route from
 * `PrototypeSwitcher`. See /prototype skill (UI.md). Throw away once a
 * direction is chosen and folded into App.tsx.
 */

export interface LandingHeroProps {
  hasCanvases: boolean;
  loading: boolean;
  onCreateCanvas: () => void;
  onImportClick: () => void;
  onChatClick: () => void;
  fileInputRef: RefObject<HTMLInputElement | null>;
}

/** Baseline — today's shipped design, kept here only so it's directly comparable. */
export function VariantCurrent({ hasCanvases, loading, onCreateCanvas, onImportClick, onChatClick }: LandingHeroProps) {
  return (
    <>
      <div className="absolute top-1/4 left-1/3 w-[500px] h-[500px] bg-[var(--color-accent)] opacity-[0.03] rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/3 w-[400px] h-[400px] bg-[var(--color-secondary)] opacity-[0.02] rounded-full blur-[100px] pointer-events-none" />
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-gradient-to-tr from-slate-500 to-zinc-400 opacity-[0.03] rounded-full blur-[130px] pointer-events-none" />
      <div className={`grid grid-cols-1 ${hasCanvases ? "md:grid-cols-3" : "md:grid-cols-2"} gap-6 w-full max-w-4xl mb-12 relative z-10`}>
        <button
          onClick={onCreateCanvas}
          disabled={loading}
          className="group relative flex flex-col items-start p-6 rounded-2xl bg-gradient-to-br from-[var(--color-surface)] to-[var(--color-elevated)] border border-[var(--color-border-default)] hover:border-[var(--color-accent)] transition-all duration-300 text-left shadow-[0_4px_20px_rgba(0,0,0,0.35)] disabled:opacity-40"
        >
          <div className="w-12 h-12 rounded-xl bg-[var(--color-accent-subtle)] border border-[var(--color-border-default)] flex items-center justify-center text-[var(--color-accent)] group-hover:scale-110 transition-transform duration-300 mb-4 shadow-inner">
            <Plus className="w-6 h-6" />
          </div>
          <h3 className="text-lg font-semibold text-[var(--color-text-primary)] mb-1">New Canvas</h3>
          <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">
            Start building a custom multi-agent system from scratch using the interactive visual node designer.
          </p>
        </button>
        <button
          onClick={onImportClick}
          disabled={loading}
          className="group relative flex flex-col items-start p-6 rounded-2xl bg-gradient-to-br from-[var(--color-surface)] to-[var(--color-elevated)] border border-[var(--color-border-default)] hover:border-[var(--color-secondary)] transition-all duration-300 text-left shadow-[0_4px_20px_rgba(0,0,0,0.35)] disabled:opacity-40"
        >
          <div className="w-12 h-12 rounded-xl bg-[var(--color-secondary-subtle)] border border-[var(--color-border-default)] flex items-center justify-center text-[var(--color-secondary)] group-hover:scale-110 transition-transform duration-300 mb-4 shadow-inner">
            <Upload className="w-6 h-6" />
          </div>
          <h3 className="text-lg font-semibold text-[var(--color-text-primary)] mb-1">Import Canvas</h3>
          <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">
            Upload a `.zip` archive or `.json` file containing agent configurations, custom tool code, and RAG document artifacts.
          </p>
        </button>
        {hasCanvases && (
          <button
            onClick={onChatClick}
            disabled={loading}
            className="group relative flex flex-col items-start p-6 rounded-2xl bg-gradient-to-br from-[var(--color-surface)] to-[var(--color-elevated)] border border-[var(--color-border-default)] hover:border-[var(--color-agent)] transition-all duration-300 text-left shadow-[0_4px_20px_rgba(0,0,0,0.35)] disabled:opacity-40"
          >
            <div className="w-12 h-12 rounded-xl bg-[var(--color-agent-subtle)] border border-[var(--color-border-default)] flex items-center justify-center text-[var(--color-agent)] group-hover:scale-110 transition-transform duration-300 mb-4 shadow-inner">
              <MessageSquare className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-semibold text-[var(--color-text-primary)] mb-1">Agent Chat</h3>
            <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">
              Start chatting with your agent workflow, ask questions, run tool actions, and orchestrate agent task completion.
            </p>
          </button>
        )}
      </div>
    </>
  );
}

/**
 * Variant A — "Node board": the three actions ARE nodes on a mini live
 * graph, positioned and wired with the same dashed/solid edge language as
 * CustomEdge.tsx, instead of an equal-weight card grid.
 */
export function VariantA({ hasCanvases, loading, onCreateCanvas, onImportClick, onChatClick }: LandingHeroProps) {
  return (
    <div
      className="relative w-full max-w-4xl mb-12 rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-surface)]/40 overflow-hidden"
      style={{
        backgroundImage:
          "radial-gradient(circle at 1px 1px, var(--color-border-default) 1px, transparent 0)",
        backgroundSize: "24px 24px",
      }}
    >
      <svg
        className="absolute inset-0 w-full h-full pointer-events-none"
        viewBox="0 0 100 60"
        preserveAspectRatio="none"
      >
        <path
          d="M 20 15 C 45 15, 45 45, 70 45"
          fill="none"
          stroke="var(--color-text-tertiary)"
          strokeWidth="0.4"
          strokeOpacity="0.4"
          vectorEffect="non-scaling-stroke"
        />
        {hasCanvases && (
          <path
            d="M 20 15 C 45 15, 45 15, 78 15"
            fill="none"
            stroke="var(--color-agent)"
            strokeWidth="0.5"
            strokeOpacity="0.7"
            strokeDasharray="1.5 1"
            vectorEffect="non-scaling-stroke"
          />
        )}
      </svg>

      <div className="relative p-10 min-h-[280px]">
        <button
          onClick={onCreateCanvas}
          disabled={loading}
          className="group absolute left-[8%] top-[15%] -translate-y-1/2 w-48 rounded-xl bg-[var(--color-surface)] border border-[var(--color-accent)]/40 hover:border-[var(--color-accent)] shadow-[0_8px_24px_-6px_rgba(0,0,0,0.4)] transition-all disabled:opacity-40 text-left"
        >
          <div className="flex items-center gap-2 px-3 py-2 rounded-t-xl bg-[var(--color-accent-surface)] border-b border-[var(--color-accent)]/10">
            <Brain className="w-3.5 h-3.5 text-[var(--color-accent)]" />
            <span className="text-[13px] font-semibold text-[var(--color-text-primary)]">New Canvas</span>
          </div>
          <p className="px-3 py-2 text-[11px] text-[var(--color-text-tertiary)] leading-relaxed">
            Start from scratch
          </p>
          <span className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-2 h-2 rounded-full bg-[var(--color-accent)] border-2 border-[var(--color-surface)]" />
        </button>

        <button
          onClick={onImportClick}
          disabled={loading}
          className="group absolute left-[45%] top-[70%] -translate-y-1/2 w-48 rounded-xl bg-[var(--color-surface)] border border-[var(--color-info)]/40 hover:border-[var(--color-info)] shadow-[0_8px_24px_-6px_rgba(0,0,0,0.4)] transition-all disabled:opacity-40 text-left"
        >
          <span className="absolute -top-1 left-1/2 -translate-x-1/2 w-2 h-2 rounded-full bg-[var(--color-info)] border-2 border-[var(--color-surface)]" />
          <div className="flex items-center gap-2 px-3 py-2 rounded-t-xl bg-[var(--color-info-surface)] border-b border-[var(--color-info)]/10">
            <Wrench className="w-3.5 h-3.5 text-[var(--color-info)]" />
            <span className="text-[13px] font-semibold text-[var(--color-text-primary)]">Import Canvas</span>
          </div>
          <p className="px-3 py-2 text-[11px] text-[var(--color-text-tertiary)] leading-relaxed">
            Bring a .zip or .json
          </p>
        </button>

        {hasCanvases && (
          <button
            onClick={onChatClick}
            disabled={loading}
            className="group absolute left-[72%] top-[25%] -translate-y-1/2 w-48 rounded-xl bg-[var(--color-surface)] border border-[var(--color-agent)]/40 hover:border-[var(--color-agent)] shadow-[0_8px_24px_-6px_rgba(0,0,0,0.4)] transition-all disabled:opacity-40 text-left"
          >
            <div className="flex items-center gap-2 px-3 py-2 rounded-t-xl bg-[var(--color-agent-surface)] border-b border-[var(--color-agent)]/10">
              <GitBranch className="w-3.5 h-3.5 text-[var(--color-agent)]" />
              <span className="text-[13px] font-semibold text-[var(--color-text-primary)]">Agent Chat</span>
            </div>
            <p className="px-3 py-2 text-[11px] text-[var(--color-text-tertiary)] leading-relaxed">
              Talk to your workflow
            </p>
            <span className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-2 h-2 rounded-full bg-[var(--color-agent)] border-2 border-[var(--color-surface)]" />
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * Variant B — "Node-styled cards": familiar 3-up grid, but each card's
 * chrome literally mirrors AgentNode/ToolNode (colored header strip, role
 * badge, decorative handle dots). Ambient blur orbs swapped for the same
 * dot-grid the real canvas uses.
 */
export function VariantB({ hasCanvases, loading, onCreateCanvas, onImportClick, onChatClick }: LandingHeroProps) {
  return (
    <>
      <div
        className="absolute inset-0 pointer-events-none opacity-60"
        style={{
          backgroundImage:
            "radial-gradient(circle at 1px 1px, var(--color-border-default) 1px, transparent 0)",
          backgroundSize: "24px 24px",
        }}
      />
      <div className={`grid grid-cols-1 ${hasCanvases ? "md:grid-cols-3" : "md:grid-cols-2"} gap-6 w-full max-w-4xl mb-12 relative z-10`}>
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
    </>
  );
}

/**
 * Variant C — "Live sketch backdrop": a compact, low-chrome action list on
 * the left; a purely decorative animated node/edge sketch (reusing the
 * existing dot-pulse/glow-active-pulse keyframes) on the right previewing
 * the product's visual language as illustration rather than as buttons.
 */
export function VariantC({ hasCanvases, loading, onCreateCanvas, onImportClick, onChatClick }: LandingHeroProps) {
  const rows = [
    {
      icon: Plus,
      label: "New Canvas",
      desc: "Start building from scratch.",
      color: "var(--color-accent)",
      onClick: onCreateCanvas,
    },
    {
      icon: Upload,
      label: "Import Canvas",
      desc: "Upload a .zip or .json file.",
      color: "var(--color-info)",
      onClick: onImportClick,
    },
    ...(hasCanvases
      ? [
          {
            icon: MessageSquare,
            label: "Agent Chat",
            desc: "Talk to your agent workflow.",
            color: "var(--color-agent)",
            onClick: onChatClick,
          },
        ]
      : []),
  ];

  return (
    <div className="w-full max-w-4xl mb-12 grid grid-cols-1 md:grid-cols-[1.1fr_0.9fr] gap-8 items-center relative z-10">
      <div className="flex flex-col divide-y divide-[var(--color-border-subtle)] rounded-xl border border-[var(--color-border-default)] bg-[var(--color-surface)]/60 overflow-hidden">
        {rows.map((row) => (
          <button
            key={row.label}
            onClick={row.onClick}
            disabled={loading}
            className="group flex items-center gap-3 px-4 py-3.5 text-left hover:bg-[var(--color-elevated)] transition-colors disabled:opacity-40"
          >
            <row.icon className="w-4 h-4 shrink-0" style={{ color: row.color }} />
            <div className="flex-1 min-w-0">
              <p className="text-[13px] font-semibold text-[var(--color-text-primary)]">{row.label}</p>
              <p className="text-[11px] text-[var(--color-text-tertiary)] truncate">{row.desc}</p>
            </div>
          </button>
        ))}
      </div>

      <div className="hidden md:block relative h-40" aria-hidden="true">
        <svg className="absolute inset-0 w-full h-full" viewBox="0 0 100 60" preserveAspectRatio="xMidYMid meet">
          <path d="M 10 45 C 35 45, 35 15, 55 15" fill="none" stroke="var(--color-agent)" strokeWidth="0.6" strokeDasharray="2 2" strokeOpacity="0.6" vectorEffect="non-scaling-stroke" />
          <path d="M 55 15 C 70 15, 70 45, 90 45" fill="none" stroke="var(--color-text-tertiary)" strokeWidth="0.5" strokeOpacity="0.4" vectorEffect="non-scaling-stroke" />
        </svg>
        <span className="absolute rounded-full bg-[var(--color-accent)] w-3 h-3 dot-pulse" style={{ left: "10%", top: "75%" }} />
        <span className="absolute rounded-full bg-[var(--color-agent)] w-3 h-3 dot-pulse" style={{ left: "55%", top: "25%", animationDelay: "0.2s" }} />
        <span className="absolute rounded-full bg-[var(--color-info)] w-3 h-3 dot-pulse" style={{ left: "90%", top: "75%", animationDelay: "0.4s" }} />
      </div>
    </div>
  );
}
