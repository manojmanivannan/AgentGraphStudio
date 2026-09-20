import { create } from "zustand";
import type { Node, Edge } from "@xyflow/react";

type SaveStatus = "idle" | "saving" | "saved" | "error";

type Viewport = { x: number; y: number; zoom: number };

interface CanvasStore {
  canvasId: string | null;
  canvasName: string;
  nodes: Node[];
  edges: Edge[];
  isDirty: boolean;
  selectedNodeId: string | null;
  activeNodeId: string | null;
  saveStatus: SaveStatus;
  viewport: Viewport;
  propertiesWidth: number;
  isDraggingPanel: boolean;
  sidebarCollapsed: boolean;

  setCanvas: (id: string, name: string) => void;
  setName: (name: string) => void;
  setNodes: (nodes: Node[]) => void;
  setNodesSilently: (nodes: Node[]) => void;
  setEdges: (edges: Edge[]) => void;
  setEdgesSilently: (edges: Edge[]) => void;
  setIsDirty: (dirty: boolean) => void;
  selectNode: (id: string | null) => void;
  setActiveNodeId: (id: string | null) => void;
  setSaveStatus: (status: SaveStatus) => void;
  setViewport: (viewport: Viewport) => void;
  setPropertiesWidth: (width: number) => void;
  setIsDraggingPanel: (isDragging: boolean) => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  reset: () => void;
}

export const useCanvasStore = create<CanvasStore>((set) => ({
  canvasId: null,
  canvasName: "Untitled Canvas",
  nodes: [],
  edges: [],
  isDirty: false,
  selectedNodeId: null,
  activeNodeId: null,
  saveStatus: "idle",
  viewport: { x: 0, y: 0, zoom: 1 },
  propertiesWidth: 320,
  isDraggingPanel: false,
  sidebarCollapsed: typeof localStorage !== "undefined" ? localStorage.getItem("sidebarCollapsed") === "true" : false,

  setCanvas: (id, name) => set({ canvasId: id, canvasName: name }),
  setName: (name) => set({ canvasName: name, isDirty: true }),
  setNodes: (nodes) => set({ nodes, isDirty: true }),
  // Updates node geometry/selection without marking the canvas dirty. Used for
  // transient ReactFlow changes (position drags, node selection) that are not
  // user edits and should not trip the unsaved-changes guard.
  setNodesSilently: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges, isDirty: true }),
  // Updates edge selection without marking the canvas dirty. Used for transient
  // ReactFlow changes (edge selection) that are not user edits and should not
  // trip the unsaved-changes guard.
  setEdgesSilently: (edges) => set({ edges }),
  setIsDirty: (isDirty) => set({ isDirty }),
  selectNode: (id) => set({ selectedNodeId: id }),
  setActiveNodeId: (id) => set({ activeNodeId: id }),
  setSaveStatus: (status) => set({ saveStatus: status }),
  setViewport: (viewport) => set({ viewport }),
  setPropertiesWidth: (propertiesWidth) => set({ propertiesWidth }),
  setIsDraggingPanel: (isDraggingPanel) => set({ isDraggingPanel }),
  setSidebarCollapsed: (sidebarCollapsed) => {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem("sidebarCollapsed", String(sidebarCollapsed));
    }
    set({ sidebarCollapsed });
  },
  reset: () =>
    set({
      canvasId: null,
      canvasName: "Untitled Canvas",
      nodes: [],
      edges: [],
      isDirty: false,
      selectedNodeId: null,
      activeNodeId: null,
      saveStatus: "idle",
      viewport: { x: 0, y: 0, zoom: 1 },
      propertiesWidth: 320,
      isDraggingPanel: false,
    }),
}));