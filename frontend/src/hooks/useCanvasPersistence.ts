import { useEffect } from "react";
import { useCanvasStore } from "@/store/canvasStore";
import { saveCanvas } from "@/lib/api";
import { encodeCanvasGraph } from "@/lib/canvasGraphCodec";

export async function saveCanvasNow(): Promise<boolean> {
  const { canvasId, canvasName, nodes, edges } = useCanvasStore.getState();
  if (!canvasId) return false;

  useCanvasStore.getState().setSaveStatus("saving");

  const payload = encodeCanvasGraph({
    canvasName,
    nodes,
    edges,
  });

  try {
    await saveCanvas(canvasId, payload);
    useCanvasStore.getState().setIsDirty(false);
    useCanvasStore.getState().setSaveStatus("saved");
    setTimeout(() => {
      useCanvasStore.getState().setSaveStatus("idle");
    }, 3000);
    return true;
  } catch (err) {
    console.error("Save failed:", err);
    useCanvasStore.getState().setSaveStatus("error");
    setTimeout(() => {
      useCanvasStore.getState().setSaveStatus("idle");
    }, 3000);
    return false;
  }
}

export function useUnsavedChangesWarning() {
  useEffect(() => {
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!useCanvasStore.getState().isDirty) return;
      event.preventDefault();
      event.returnValue = "";
    };

    window.addEventListener("beforeunload", handleBeforeUnload);

    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
    };
  }, []);
}

export function useSaveShortcut() {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const isSaveShortcut =
        (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s";
      if (!isSaveShortcut) return;

      event.preventDefault();
      void saveCanvasNow();
    };

    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, []);
}