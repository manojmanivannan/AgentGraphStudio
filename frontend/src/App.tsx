import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { useCanvasStore } from "@/store/canvasStore";
import { createCanvas, listCanvases, getCanvas } from "@/lib/api";
import { Plus, FileText } from "lucide-react";
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
        data: {
          id: a.id,
          name: a.name,
          role: a.role,
          instructions: a.instructions,
          modelName: a.model_name,
          agentType: a.agent_type,
        } as any,
      }));

      const toolNodes: Node[] = canvas.nodes.tools.map((t) => ({
        id: t.id,
        type: "tool" as const,
        position: { x: t.position_x, y: t.position_y },
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
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="w-full max-w-md p-8">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-gray-800 mb-2">Agent Builder</h1>
          <p className="text-sm text-gray-500">Build AI agent workflows visually</p>
        </div>

        <button
          onClick={handleCreateCanvas}
          disabled={loading}
          className="w-full flex items-center justify-center gap-2 px-4 py-3 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg transition-colors mb-6 disabled:opacity-50"
        >
          <Plus className="w-4 h-4" />
          New Canvas
        </button>

        {canvases.length > 0 && (
          <div>
            <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
              Recent Canvases
            </h2>
            <div className="space-y-1">
              {canvases.map((c) => (
                <button
                  key={c.id}
                  onClick={() => handleOpenCanvas(c.id)}
                  disabled={loading}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-gray-700 hover:bg-white hover:shadow-sm rounded-lg transition-all disabled:opacity-50 border border-transparent hover:border-gray-200"
                >
                  <FileText className="w-4 h-4 text-gray-400" />
                  {c.name}
                </button>
              ))}
            </div>
          </div>
        )}

        {loading && (
          <div className="flex justify-center mt-6">
            <span className="w-5 h-5 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />
          </div>
        )}
      </div>
    </div>
  );
}
