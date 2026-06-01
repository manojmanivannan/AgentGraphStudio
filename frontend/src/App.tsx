import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { useCanvasStore } from "@/store/canvasStore";
import { createCanvas, listCanvases, getCanvas } from "@/lib/api";
import { Plus, FileText, Workflow } from "lucide-react";
import type { AgentNodeData, ToolNodeData } from "@/types";
import type { Node } from "@xyflow/react";

export default function App() {
  const canvasId = useCanvasStore((s) => s.canvasId);
  const setCanvas = useCanvasStore((s) => s.setCanvas);
  const setNodes = useCanvasStore((s) => s.setNodes);
  const setEdges = useCanvasStore((s) => s.setEdges);
  const [canvases, setCanvases] = useState<Array<{ id: string; name: string }>>([]);
  const [loading, setLoading] = useState(false);

  const loadCanvases = async () => {
    try {
      const list = await listCanvases();
      setCanvases(list);
    } catch {
      setCanvases([]);
    }
  };

  useEffect(() => {
    loadCanvases();
  }, [canvasId]);

  // Support deep-linking via ?canvas=<id> (used by E2E tests and shareable URLs)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const initialId = params.get("canvas");
    if (initialId && !canvasId) {
      handleOpenCanvas(initialId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCreateCanvas = async () => {
    setLoading(true);
    try {
      const canvas = await createCanvas();
      setCanvas(canvas.id, canvas.name);
      setNodes([]);
      setEdges([]);
    } catch (err) {
      console.error("Failed to create canvas:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleOpenCanvas = async (id: string) => {
    setLoading(true);
    try {
      const canvas = await getCanvas(id);
      setCanvas(canvas.id, canvas.name);

      const agentNodes: Node[] = canvas.nodes.agents.map((a) => ({
        id: a.id,
        type: "agent" as const,
        position: { x: a.position_x, y: a.position_y },
        style: { width: 280 },
        data: {
          id: a.id,
          name: a.name,
          role: a.role,
          instructions: a.instructions,
          modelName: a.model_name,
          agentType: a.agent_type,
          enableMemory: a.enable_memory,
          enableConversationHistory: a.enable_conversation_history,
        } as any,
      }));

      const toolNodes: Node[] = canvas.nodes.tools.map((t) => ({
        id: t.id,
        type: "tool" as const,
        position: { x: t.position_x, y: t.position_y },
        style: { width: 220 },
        data: {
          id: t.id,
          name: t.name,
          code: t.code,
        } as any,
      }));

      setNodes([...agentNodes, ...toolNodes]);
      setEdges(
        canvas.edges.map((e) => ({
          id: e.id,
          source: e.source_node_id,
          target: e.target_node_id,
          data: { edgeType: e.edge_type },
        }))
      );
    } catch (err) {
      console.error("Failed to open canvas:", err);
    } finally {
      setLoading(false);
    }
  };

  if (canvasId) {
    return <AppShell />;
  }

  return (
    <div className="min-h-screen bg-[var(--color-base)] flex items-center justify-center noise-bg relative overflow-hidden">
      {/* Ambient background glow */}
      <div className="absolute top-1/4 left-1/3 w-[500px] h-[500px] bg-[var(--color-accent)] opacity-[0.03] rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/3 w-[400px] h-[400px] bg-[var(--color-secondary)] opacity-[0.02] rounded-full blur-[100px] pointer-events-none" />

      <div className="w-full max-w-md p-8 relative z-10" style={{ animation: "fadeIn 0.6s ease-out" }}>
        {/* Brand */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-[var(--color-accent-subtle)] border border-[var(--color-border-default)] mb-5">
            <Workflow className="w-6 h-6 text-[var(--color-accent)]" />
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-[var(--color-text-primary)] mb-2">
            Agent Builder
          </h1>
          <p className="text-sm text-[var(--color-text-tertiary)] font-light tracking-wide">
            Build AI agent workflows visually
          </p>
        </div>

        {/* New Canvas Button */}
        <button
          onClick={handleCreateCanvas}
          disabled={loading}
          data-testid="create-canvas-button"
          className="btn-primary w-full justify-center py-3 text-[13px] rounded-xl mb-8"
        >
          <Plus className="w-4 h-4" />
          New Canvas
        </button>

        {/* Recent Canvases */}
        {canvases.length > 0 && (
          <div style={{ animation: "fadeIn 0.6s ease-out 0.15s both" }}>
            <h2 className="text-[11px] font-semibold text-[var(--color-text-tertiary)] uppercase tracking-[0.1em] mb-3 px-1">
              Recent Canvases
            </h2>
            <div className="space-y-1">
              {canvases.map((c, i) => (
                <button
                  key={c.id}
                  onClick={() => handleOpenCanvas(c.id)}
                  disabled={loading}
                  className="w-full flex items-center gap-3 px-3 py-2.5 text-[13px] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-elevated)] rounded-lg transition-all duration-150 disabled:opacity-40 border border-transparent hover:border-[var(--color-border-default)]"
                  style={{ animation: `staggerFadeIn 0.4s ease-out ${0.05 * i}s both` }}
                >
                  <FileText className="w-4 h-4 text-[var(--color-text-tertiary)]" />
                  <span className="truncate flex-1 text-left">{c.name}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Loading Spinner */}
        {loading && (
          <div className="flex justify-center mt-6">
            <div className="flex gap-1.5">
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent)]"
                  style={{
                    animation: "dotPulse 1.2s ease-in-out infinite",
                    animationDelay: `${i * 0.15}s`,
                  }}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}