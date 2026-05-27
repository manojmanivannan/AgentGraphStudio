import { create } from "zustand";
import type { Node, Edge } from "@xyflow/react";

interface CanvasStore {
  canvasId: string | null;
  canvasName: string;
  nodes: Node[];
  edges: Edge[];
  selectedNodeId: string | null;
  activeNodeId: string | null;
  propertiesOpen: boolean;
  chatOpen: boolean;

  setCanvas: (id: string, name: string) => void;
  setName: (name: string) => void;
  setNodes: (nodes: Node[]) => void;
  setEdges: (edges: Edge[]) => void;
  selectNode: (id: string | null) => void;
  setActiveNodeId: (id: string | null) => void;
  toggleProperties: () => void;
  toggleChat: () => void;
  reset: () => void;
}

export const useCanvasStore = create<CanvasStore>((set) => ({
  canvasId: null,
  canvasName: "Untitled Canvas",
  nodes: [],
  edges: [],
  selectedNodeId: null,
  activeNodeId: null,
  propertiesOpen: false,
  chatOpen: false,

  setCanvas: (id, name) => set({ canvasId: id, canvasName: name }),
  setName: (name) => set({ canvasName: name }),
  setNodes: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges }),
  selectNode: (id) => set({ selectedNodeId: id, propertiesOpen: id !== null }),
  setActiveNodeId: (id) => set({ activeNodeId: id }),
  toggleProperties: () => set((s) => ({ propertiesOpen: !s.propertiesOpen })),
  toggleChat: () => set((s) => ({ chatOpen: !s.chatOpen })),
  reset: () =>
    set({
      canvasId: null,
      canvasName: "Untitled Canvas",
      nodes: [],
      edges: [],
      selectedNodeId: null,
      activeNodeId: null,
      propertiesOpen: false,
      chatOpen: false,
    }),
}));
