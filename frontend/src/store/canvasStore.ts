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
  saveStatus: SaveStatus;
  viewport: Viewport;
  propertiesWidth: number;
  isDraggingPanel: boolean;

  setCanvas: (id: string, name: string) => void;
  setName: (name: string) => void;
  setNodes: (nodes: Node[]) => void;
  setEdges: (edges: Edge[]) => void;
  selectNode: (id: string | null) => void;
  setActiveNodeId: (id: string | null) => void;
  setSaveStatus: (status: SaveStatus) => void;
  setViewport: (viewport: Viewport) => void;
  setPropertiesWidth: (width: number) => void;
  setIsDraggingPanel: (isDragging: boolean) => void;
  reset: () => void;
}

export const useCanvasStore = create<CanvasStore>((set) => ({
  canvasId: null,
  canvasName: "Untitled Canvas",
  nodes: [],
  edges: [],
  selectedNodeId: null,
  activeNodeId: null,
  saveStatus: "idle",
  viewport: { x: 0, y: 0, zoom: 1 },
  propertiesWidth: 320,
  isDraggingPanel: false,

  setCanvas: (id, name) => set({ canvasId: id, canvasName: name }),
  setName: (name) => set({ canvasName: name }),
  setNodes: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges }),
  selectNode: (id) => set({ selectedNodeId: id }),
  setActiveNodeId: (id) => set({ activeNodeId: id }),
  setSaveStatus: (status) => set({ saveStatus: status }),
  setViewport: (viewport) => set({ viewport }),
  setPropertiesWidth: (propertiesWidth) => set({ propertiesWidth }),
  setIsDraggingPanel: (isDraggingPanel) => set({ isDraggingPanel }),
  reset: () =>
    set({
      canvasId: null,
      canvasName: "Untitled Canvas",
      nodes: [],
      edges: [],
      selectedNodeId: null,
      activeNodeId: null,
      saveStatus: "idle",
      viewport: { x: 0, y: 0, zoom: 1 },
      propertiesWidth: 320,
      isDraggingPanel: false,
    }),
}));