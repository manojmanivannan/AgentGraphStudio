import { useEffect } from "react";
import { useCanvasHistoryStore } from "@/store/canvasHistoryStore";

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
}

export function useCanvasUndoRedoShortcuts() {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (isEditableTarget(event.target)) return;
      if (!event.metaKey && !event.ctrlKey) return;

      const key = event.key.toLowerCase();

      if (key === "y" || (event.shiftKey && key === "z")) {
        event.preventDefault();
        useCanvasHistoryStore.getState().redo();
        return;
      }

      if (key === "z") {
        event.preventDefault();
        useCanvasHistoryStore.getState().undo();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);
}
