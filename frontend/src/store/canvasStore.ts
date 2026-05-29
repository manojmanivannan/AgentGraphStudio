import { create } from "zustand";
import type { Node, Edge } from "@xyflow/react";

type SaveStatus = "idle" | "saving" | "saved" | "error";

type Viewport = { x: number; y: number; zoom: number };

interface CanvasStore {
  canvasId: string | null;
  canvasName: string;
  nodes: Node[];
  edges: Edge[];
  selectedNodeId: string | null;
  activeNodeId: string | null;
  chatOpen: boolean;
  observabilityOpen: boolean;
  saveStatus: SaveStatus;
  viewport: Viewport;

  setCanvas: (id: string, name: string) => void;
  setName: (name: string) => void;
  setNodes: (nodes: Node[]) => void;
  setEdges: (edges: Edge[]) => void;
  selectNode: (id: string | null) => void;
  setActiveNodeId: (id: string | null) => void;
  toggleChat: () => void;
  toggleObservability: () => void;
  setSaveStatus: (status: SaveStatus) => void;
  setViewport: (viewport: Viewport) => void;
  reset: () => void;
}

export const useCanvasStore = create<CanvasStore>((set) => ({
  canvasId: null,
  canvasName: "Untitled Canvas",
  nodes: [],
  edges: [],
  selectedNodeId: null,
  activeNodeId: null,
  chatOpen: false,
  observabilityOpen: false,
  saveStatus: "idle",
  viewport: { x: 0, y: 0, zoom: 1 },

  setCanvas: (id, name) => set({ canvasId: id, canvasName: name }),
  setName: (name) => set({ canvasName: name }),
  setNodes: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges }),
  selectNode: (id) => set({ selectedNodeId: id }),
  setActiveNodeId: (id) => set({ activeNodeId: id }),
  toggleChat: () => set((s) => ({ chatOpen: !s.chatOpen })),
  toggleObservability: () => set((s) => ({ observabilityOpen: !s.observabilityOpen })),
  setSaveStatus: (status) => set({ saveStatus: status }),
  setViewport: (viewport) => set({ viewport }),
  reset: () =>
    set({
      canvasId: null,
      canvasName: "Untitled Canvas",
      nodes: [],
      edges: [],
      selectedNodeId: null,
      activeNodeId: null,
      chatOpen: false,
      observabilityOpen: false,
      saveStatus: "idle",
      viewport: { x: 0, y: 0, zoom: 1 },
    }),
}));