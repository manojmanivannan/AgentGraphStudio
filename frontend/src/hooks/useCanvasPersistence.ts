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
  const statusTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!canvasId) return;

    const payload: CanvasSavePayload = {
      name: canvasName,
      nodes: {
        agents: nodes
          .filter((n) => n.type === "agent")
          .map((n) => ({
            id: n.id,
            name: (n.data?.name as string) || "Agent",
            role: (n.data?.role as string) || "",
            instructions: (n.data?.instructions as string) || "",
            model_name: (n.data?.modelName as string) || "ollama:llama3.1",
            agent_type: (n.data?.agentType as string) || "worker",
            enable_memory: (n.data?.enableMemory as boolean) ?? false,
            enable_conversation_history: (n.data?.enableConversationHistory as boolean) ?? false,
            position_x: n.position.x,
            position_y: n.position.y,
          })),
        tools: nodes
          .filter((n) => n.type === "tool")
          .map((n) => ({
            id: n.id,
            name: (n.data?.name as string) || "Tool",
            code: (n.data?.code as string) || "",
            args: (n.data?.args as []) || [],
            position_x: n.position.x,
            position_y: n.position.y,
          })),
      },
      edges: edges.map((e) => ({
        id: e.id,
        source_node_id: e.source,
        target_node_id: e.target,
        edge_type: (e.data?.edgeType as string) || "tool_access",
      })),
    };

    const serialized = JSON.stringify(payload);
    if (serialized === prevDataRef.current) return;
    prevDataRef.current = serialized;

    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (statusTimeoutRef.current) clearTimeout(statusTimeoutRef.current);

    debounceRef.current = setTimeout(async () => {
      useCanvasStore.getState().setSaveStatus("saving");
      try {
        await saveCanvas(canvasId, payload);
        useCanvasStore.getState().setSaveStatus("saved");
        statusTimeoutRef.current = setTimeout(() => {
          useCanvasStore.getState().setSaveStatus("idle");
        }, 3000);
      } catch (err) {
        console.error("Auto-save failed:", err);
        useCanvasStore.getState().setSaveStatus("error");
        statusTimeoutRef.current = setTimeout(() => {
          useCanvasStore.getState().setSaveStatus("idle");
        }, 3000);
      }
    }, 500);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      if (statusTimeoutRef.current) clearTimeout(statusTimeoutRef.current);
    };
  }, [canvasId, canvasName, nodes, edges]);
}