import { useEffect, useRef } from "react";
import { useCanvasStore } from "@/store/canvasStore";
import { saveCanvas } from "@/lib/api";
import { encodeCanvasGraph } from "@/lib/canvasGraphCodec";

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

    const payload = encodeCanvasGraph({
      canvasName,
      nodes,
      edges,
    });

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