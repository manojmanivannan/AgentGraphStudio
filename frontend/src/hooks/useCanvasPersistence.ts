import { useEffect, useRef } from "react";
import { useCanvasStore } from "@/store/canvasStore";
import { saveCanvas } from "@/lib/api";
import type { CanvasSavePayload } from "@/types";

export function useCanvasPersistence() {
  const canvasId = useCanvasStore((s) => s.canvasId);
  const canvasName = useCanvasStore((s) => s.canvasName);
  const nodes = useCanvasStore((s) => s.nodes);
  const edges = useCanvasStore((s) => s.edges);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prevDataRef = useRef<string>("");

  useEffect(() => {
    if (!canvasId) return;

    const payload: CanvasSavePayload = {
      name: canvasName,
      nodes: {
        agents: nodes
          .filter((n) => n.type === "agent")
          .map((n) => ({
            id: n.id,
            name: n.data?.name || "Agent",
            role: n.data?.role || "",
            instructions: n.data?.instructions || "",
            model_name: n.data?.modelName || "ollama:llama3.1",
            agent_type: n.data?.agentType || "worker",
            position_x: n.position.x,
            position_y: n.position.y,
          })),
        tools: nodes
          .filter((n) => n.type === "tool")
          .map((n) => ({
            id: n.id,
            name: n.data?.name || "Tool",
            code: n.data?.code || "",
            position_x: n.position.x,
            position_y: n.position.y,
          })),
      },
      edges: edges.map((e) => ({
        id: e.id,
        source_node_id: e.source,
        target_node_id: e.target,
        edge_type: e.data?.edgeType || "tool_access",
      })),
    };

    const serialized = JSON.stringify(payload);
    if (serialized === prevDataRef.current) return;
    prevDataRef.current = serialized;

    if (debounceRef.current) clearTimeout(debounceRef.current);

    debounceRef.current = setTimeout(async () => {
      try {
        await saveCanvas(canvasId, payload);
      } catch (err) {
        console.error("Auto-save failed:", err);
      }
    }, 500);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [canvasId, canvasName, nodes, edges]);
}
