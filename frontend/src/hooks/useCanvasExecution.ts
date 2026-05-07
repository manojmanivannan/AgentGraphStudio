import { useRef } from "react";
import { useCanvasStore } from "@/store/canvasStore";
import type { ExecutionEvent } from "@/types";

export function useCanvasExecution() {
  const wsRef = useRef<WebSocket | null>(null);
  const addEvent = useCanvasStore((s) => s.addExecutionEvent);
  const setStatus = useCanvasStore((s) => s.setExecutionStatus);
  const executionStatus = useCanvasStore((s) => s.executionStatus);

  const run = (canvasId: string, prompt: string) => {
    if (executionStatus === "running") return;

    useCanvasStore.getState().clearExecution();
    useCanvasStore.getState().setExecutionStatus("running");

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = import.meta.env.VITE_API_HOST || "localhost:8000";
    const ws = new WebSocket(`${protocol}//${host}/ws/canvases/${canvasId}/run`);

    ws.onopen = () => {
      ws.send(JSON.stringify({ prompt }));
    };

    ws.onmessage = (evt) => {
      const event = JSON.parse(evt.data) as ExecutionEvent;
      addEvent(event);
      if (event.type === "run_complete") setStatus("done");
      if (event.type === "error") setStatus("error");
    };

    ws.onerror = () => {
      setStatus("error");
      addEvent({ type: "error", message: "WebSocket connection error" });
    };

    ws.onclose = () => {
      if (wsRef.current === ws) wsRef.current = null;
    };

    wsRef.current = ws;
  };

  const abort = () => {
    wsRef.current?.close();
    setStatus("idle");
  };

  return { run, abort };
}
