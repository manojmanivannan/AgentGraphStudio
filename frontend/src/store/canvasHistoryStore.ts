import type { Edge, Node } from "@xyflow/react";
import { create } from "zustand";
import { useCanvasStore } from "@/store/canvasStore";

const BURST_DEBOUNCE_MS = 400;
const MAX_PAST_SNAPSHOTS = 50;

interface Snapshot {
  nodes: Node[];
  edges: Edge[];
}

interface CanvasHistoryStore {
  past: Snapshot[];
  future: Snapshot[];
  applying: boolean;
  canUndo: () => boolean;
  canRedo: () => boolean;
  undo: () => void;
  redo: () => void;
}

let burstStart: Snapshot | null = null;
let burstTimer: ReturnType<typeof setTimeout> | null = null;

function appendPastSnapshot(past: Snapshot[], snapshot: Snapshot): Snapshot[] {
  return [...past, snapshot].slice(-MAX_PAST_SNAPSHOTS);
}

function clearBurstTimer() {
  if (burstTimer !== null) {
    clearTimeout(burstTimer);
    burstTimer = null;
  }
}

function cancelPendingBurst() {
  clearBurstTimer();
  burstStart = null;
}

function getCanvasSnapshot(): Snapshot {
  const { nodes, edges } = useCanvasStore.getState();
  return { nodes, edges };
}

function commitPendingBurst() {
  if (burstStart === null) return;

  const snapshot = burstStart;
  burstStart = null;
  burstTimer = null;

  useCanvasHistoryStore.setState((state) => ({
    past: appendPastSnapshot(state.past, snapshot),
    future: [],
  }));
}

export const useCanvasHistoryStore = create<CanvasHistoryStore>((set, get) => ({
  past: [],
  future: [],
  applying: false,
  canUndo: () => get().past.length > 0,
  canRedo: () => get().future.length > 0,
  undo: () => {
    const { past, future } = get();
    if (past.length === 0) return;

    cancelPendingBurst();

    const previousSnapshot = past[past.length - 1];
    const currentSnapshot = getCanvasSnapshot();
    const canvasStore = useCanvasStore.getState();

    set({ applying: true });
    canvasStore.setNodes(previousSnapshot.nodes);
    canvasStore.setEdges(previousSnapshot.edges);
    set({
      past: past.slice(0, -1),
      future: [currentSnapshot, ...future],
      applying: false,
    });
  },
  redo: () => {
    const { past, future } = get();
    if (future.length === 0) return;

    cancelPendingBurst();

    const [nextSnapshot, ...remainingFuture] = future;
    const currentSnapshot = getCanvasSnapshot();
    const canvasStore = useCanvasStore.getState();

    set({ applying: true });
    canvasStore.setNodes(nextSnapshot.nodes);
    canvasStore.setEdges(nextSnapshot.edges);
    set({
      past: appendPastSnapshot(past, currentSnapshot),
      future: remainingFuture,
      applying: false,
    });
  },
}));

export function resetCanvasHistory(): void {
  cancelPendingBurst();
  useCanvasHistoryStore.setState({
    past: [],
    future: [],
    applying: false,
  });
}

useCanvasStore.subscribe((state, previousState) => {
  if (useCanvasHistoryStore.getState().applying) return;

  const canvasChanged = state.nodes !== previousState.nodes || state.edges !== previousState.edges;
  if (!canvasChanged) return;

  if (burstStart === null) {
    burstStart = {
      nodes: previousState.nodes,
      edges: previousState.edges,
    };
  }

  clearBurstTimer();
  burstTimer = setTimeout(commitPendingBurst, BURST_DEBOUNCE_MS);
});

export type { CanvasHistoryStore, Snapshot };
