import { useEffect } from "react";
import { useCanvasStore } from "@/store/canvasStore";
import { deleteSelectedNodesWithConfirm } from "@/lib/nodeDeletion";

const DELETE_KEYS = new Set(["Backspace", "Delete"]);

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
}

/**
 * Global Delete/Backspace handler for the canvas: deletes every selected
 * node (with a confirmation dialog) instead of ReactFlow's default silent
 * removal. Ignored while focus is inside an editable element (inputs,
 * textareas, the Monaco code editor, etc.) so it never eats a keystroke
 * meant for text editing.
 */
export function useCanvasDeleteKeyHandler() {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (!DELETE_KEYS.has(event.key)) return;
      if (isEditableTarget(event.target)) return;

      const hasSelectedNode = useCanvasStore.getState().nodes.some((n) => n.selected);
      if (!hasSelectedNode) return;

      event.preventDefault();
      void deleteSelectedNodesWithConfirm();
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);
}
