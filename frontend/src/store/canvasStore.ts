import { create } from "zustand";
import type { Node, Edge } from "@xyflow/react";
import type { ExecutionEvent, ExecutionStatus } from "@/types";

interface CanvasStore {
  canvasId: string | null;
  canvasName: string;
  nodes: Node[];
  edges: Edge[];
  selectedNodeId: string | null;
  executionStatus: ExecutionStatus;
  executionEvents: ExecutionEvent[];

  setCanvas: (id: string, name: string) => void;
  setName: (name: string) => void;
  setNodes: (nodes: Node[]) => void;
  setEdges: (edges: Edge[]) => void;
  selectNode: (id: string | null) => void;
  addExecutionEvent: (event: ExecutionEvent) => void;
  setExecutionStatus: (status: ExecutionStatus) => void;
  clearExecution: () => void;
  reset: () => void;
}

export const useCanvasStore = create<CanvasStore>((set) => ({
  canvasId: null,
  canvasName: "Untitled Canvas",
  nodes: [],
  edges: [],
  selectedNodeId: null,
  executionStatus: "idle",
  executionEvents: [],

  setCanvas: (id, name) => set({ canvasId: id, canvasName: name }),
  setName: (name) => set({ canvasName: name }),
  setNodes: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges }),
  selectNode: (id) => set({ selectedNodeId: id }),
  addExecutionEvent: (event) =>
    set((state) => ({ executionEvents: [...state.executionEvents, event] })),
  setExecutionStatus: (status) => set({ executionStatus: status }),
  clearExecution: () => set({ executionEvents: [], executionStatus: "idle" }),
  reset: () =>
    set({
      canvasId: null,
      canvasName: "Untitled Canvas",
      nodes: [],
      edges: [],
      selectedNodeId: null,
      executionStatus: "idle",
      executionEvents: [],
    }),
}));
