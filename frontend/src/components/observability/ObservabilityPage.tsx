import { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import {
  Home,
  Layout,
  MessageSquare,
  Activity,
  FolderKanban,
  ExternalLink,
  ShieldCheck,
  Zap,
} from "lucide-react";
import { getCanvas, listConversations, createConversation } from "@/lib/api";
import { ThemeToggle } from "@/components/ThemeToggle";

const MLFLOW_PATH = "/mlflow/";

export default function ObservabilityPage() {
  const { canvas_id } = useParams<{ canvas_id: string }>();
  const navigate = useNavigate();

  const [canvasName, setCanvasName] = useState("Canvas");
  const [loading, setLoading] = useState(true);
  const [chatConvId, setChatConvId] = useState<string | null>(null);

  useEffect(() => {
    if (!canvas_id) return;

    const loadData = async () => {
      try {
        const canvas = await getCanvas(canvas_id);
        setCanvasName(canvas.name);

        const convs = await listConversations(canvas_id);
        if (convs && convs.length > 0) {
          setChatConvId(convs[0].id);
        } else {
          setChatConvId(null);
        }
      } catch (err) {
        console.error("Failed to load observability canvas metadata:", err);
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [canvas_id]);

  const handleChatClick = async () => {
    if (!canvas_id) return;
    if (chatConvId) {
      navigate(`/chat/${chatConvId}`);
    } else {
      try {
        const newConv = await createConversation(canvas_id, "New Conversation");
        navigate(`/chat/${newConv.id}`);
      } catch (err) {
        console.error("Failed to create conversation:", err);
        navigate(`/chat/empty`);
      }
    }
  };

  return (
    <div className="h-screen w-screen flex bg-[var(--color-base)] noise-bg relative overflow-hidden">
      {/* Left Sidebar Panel */}
      <aside className="w-64 h-full border-r border-[var(--color-border-subtle)] bg-[var(--color-surface)] flex flex-col z-20">
        {/* Sidebar Header */}
        <div className="p-4 border-b border-[var(--color-border-subtle)] flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <FolderKanban className="w-5 h-5 text-[var(--color-accent)]" />
            <span className="font-bold text-[14px] tracking-tight text-[var(--color-text-primary)]">
              AgentGraph Studio
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 mt-1">
            <Link
              to="/"
              className="flex items-center justify-center gap-1.5 py-1.5 rounded-lg border border-[var(--color-border-default)] hover:bg-[var(--color-elevated)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] text-xs transition-colors"
              title="Home"
            >
              <Home className="w-3.5 h-3.5" />
              Home
            </Link>
            {canvas_id && (
              <Link
                to={`/canvas/${canvas_id}`}
                className="flex items-center justify-center gap-1.5 py-1.5 rounded-lg border border-[var(--color-border-default)] hover:bg-[var(--color-elevated)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] text-xs transition-colors"
                title="Canvas Editor"
              >
                <Layout className="w-3.5 h-3.5" />
                Canvas
              </Link>
            )}
          </div>
        </div>

        {/* Sidebar Navigation Options */}
        <div className="flex-1 p-4 space-y-4 overflow-y-auto">
          <div>
            <h3 className="text-[10px] font-semibold text-[var(--color-text-tertiary)] uppercase tracking-wider mb-2">
              Orchestrate
            </h3>
            <div className="space-y-1.5">
              <Link
                to={`/canvas/${canvas_id}`}
                className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-elevated)] transition-colors"
              >
                <Layout className="w-4 h-4 text-[var(--color-text-tertiary)]" />
                Visual Canvas
              </Link>
              <button
                onClick={handleChatClick}
                className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-elevated)] transition-colors text-left cursor-pointer"
              >
                <MessageSquare className="w-4 h-4 text-[var(--color-text-tertiary)]" />
                Agent Chat
              </button>
            </div>
          </div>

          <div>
            <h3 className="text-[10px] font-semibold text-[var(--color-text-tertiary)] uppercase tracking-wider mb-2">
              Observability Info
            </h3>
            <div className="p-3.5 rounded-xl bg-[var(--color-elevated)] border border-[var(--color-border-subtle)] space-y-3">
              <div className="flex gap-2">
                <ShieldCheck className="w-4 h-4 text-[var(--color-success)] shrink-0 mt-0.5" />
                <div className="space-y-1">
                  <p className="text-[11px] font-semibold text-[var(--color-text-primary)]">
                    MLflow Tracing
                  </p>
                  <p className="text-[10px] text-[var(--color-text-tertiary)] leading-relaxed">
                    Visualise detailed execution paths, inputs, outputs, and model invocation metrics for every run.
                  </p>
                </div>
              </div>
              <div className="flex gap-2">
                <Zap className="w-4 h-4 text-[var(--color-accent)] shrink-0 mt-0.5" />
                <div className="space-y-1">
                  <p className="text-[11px] font-semibold text-[var(--color-text-primary)]">
                    Latency & Tokens
                  </p>
                  <p className="text-[10px] text-[var(--color-text-tertiary)] leading-relaxed">
                    Track performance metrics, evaluation feedback, and prompt iterations.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Sidebar Footer */}
        <div className="p-3 border-t border-[var(--color-border-subtle)] bg-[var(--color-inset)] flex items-center justify-between">
          <span className="text-[10px] text-[var(--color-text-tertiary)]">
            Powered by MLflow
          </span>
          <ThemeToggle className="hover:bg-[var(--color-elevated)]" />
        </div>
      </aside>

      {/* Main Panel */}
      <main className="flex-1 h-full flex flex-col relative z-10 overflow-hidden">
        {/* Top Header */}
        <header className="h-12 border-b border-[var(--color-border-subtle)] bg-[var(--color-surface)] flex items-center justify-between px-6 shrink-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-[var(--color-text-tertiary)] uppercase tracking-wider">
              Observability
            </span>
            <span className="text-xs text-[var(--color-text-tertiary)]">•</span>
            <span className="text-[13px] font-semibold text-[var(--color-text-primary)]">
              {canvasName}
            </span>
          </div>

          <div className="flex items-center gap-3">
            <a
              href={MLFLOW_PATH}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--color-border-default)] hover:bg-[var(--color-elevated)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] text-xs font-medium transition-all"
              title="Open MLflow in a new tab"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              Full Screen
            </a>
          </div>
        </header>

        {/* Main Content (MLflow Iframe) */}
        <div className="flex-1 bg-[var(--color-base)] relative">
          <iframe
            src={MLFLOW_PATH}
            className="w-full h-full border-none"
            title="MLflow Observability Traces"
          />
        </div>
      </main>
    </div>
  );
}
