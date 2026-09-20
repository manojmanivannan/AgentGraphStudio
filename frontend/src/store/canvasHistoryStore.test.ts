import type { Edge, Node } from "@xyflow/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useCanvasStore } from "@/store/canvasStore";
import { resetCanvasHistory, useCanvasHistoryStore } from "./canvasHistoryStore";

const BURST_DEBOUNCE_MS = 400;

function makeNode(id: string, x = 0): Node {
  return {
    id,
    type: "agent",
    position: { x, y: 0 },
    data: { name: id },
  };
}

function makeEdge(id: string, source: string, target: string): Edge {
  return {
    id,
    source,
    target,
  };
}

function advanceBurstDebounce() {
  vi.advanceTimersByTime(BURST_DEBOUNCE_MS);
}

beforeEach(() => {
  vi.useFakeTimers();
  useCanvasStore.getState().reset();
  resetCanvasHistory();
});

afterEach(() => {
  resetCanvasHistory();
  useCanvasStore.getState().reset();
  vi.clearAllTimers();
  vi.useRealTimers();
});

describe("canvasHistoryStore", () => {
  it("records one past snapshot after a single nodes change once the debounce elapses", () => {
    useCanvasStore.getState().setNodes([makeNode("node-1")]);

    expect(useCanvasHistoryStore.getState().past).toHaveLength(0);

    advanceBurstDebounce();

    expect(useCanvasHistoryStore.getState().past).toEqual([
      {
        nodes: [],
        edges: [],
      },
    ]);
  });

  it("coalesces rapid node changes into one history entry from before the first change", () => {
    useCanvasStore.getState().setNodes([makeNode("node-1", 0)]);
    vi.advanceTimersByTime(200);

    useCanvasStore.getState().setNodes([makeNode("node-1", 50)]);
    vi.advanceTimersByTime(200);

    useCanvasStore.getState().setNodes([makeNode("node-1", 100)]);
    vi.advanceTimersByTime(399);

    expect(useCanvasHistoryStore.getState().past).toHaveLength(0);

    vi.advanceTimersByTime(1);

    expect(useCanvasHistoryStore.getState().past).toEqual([
      {
        nodes: [],
        edges: [],
      },
    ]);
  });

  it("records separate bursts as separate past snapshots", () => {
    const node = makeNode("node-1");

    useCanvasStore.getState().setNodes([node]);
    advanceBurstDebounce();

    useCanvasStore.getState().setEdges([makeEdge("edge-1", "node-1", "node-2")]);
    advanceBurstDebounce();

    expect(useCanvasHistoryStore.getState().past).toEqual([
      {
        nodes: [],
        edges: [],
      },
      {
        nodes: [node],
        edges: [],
      },
    ]);
  });

  it("undo restores the previous snapshot and moves the current state into future", () => {
    const node = makeNode("node-1");
    const edge = makeEdge("edge-1", "node-1", "node-2");

    useCanvasStore.getState().setNodes([node]);
    advanceBurstDebounce();
    useCanvasStore.getState().setEdges([edge]);
    advanceBurstDebounce();

    useCanvasHistoryStore.getState().undo();

    expect(useCanvasStore.getState().nodes).toEqual([node]);
    expect(useCanvasStore.getState().edges).toEqual([]);
    expect(useCanvasHistoryStore.getState().past).toEqual([
      {
        nodes: [],
        edges: [],
      },
    ]);
    expect(useCanvasHistoryStore.getState().future).toEqual([
      {
        nodes: [node],
        edges: [edge],
      },
    ]);
  });

  it("redo restores the state that was current right before undo", () => {
    const node = makeNode("node-1");
    const edge = makeEdge("edge-1", "node-1", "node-2");

    useCanvasStore.getState().setNodes([node]);
    advanceBurstDebounce();
    useCanvasStore.getState().setEdges([edge]);
    advanceBurstDebounce();
    useCanvasHistoryStore.getState().undo();

    useCanvasHistoryStore.getState().redo();

    expect(useCanvasStore.getState().nodes).toEqual([node]);
    expect(useCanvasStore.getState().edges).toEqual([edge]);
    expect(useCanvasHistoryStore.getState().past).toEqual([
      {
        nodes: [],
        edges: [],
      },
      {
        nodes: [node],
        edges: [],
      },
    ]);
    expect(useCanvasHistoryStore.getState().future).toEqual([]);
  });

  it("clears redo history after a new committed edit following undo", () => {
    const node = makeNode("node-1");
    const edge = makeEdge("edge-1", "node-1", "node-2");
    const replacementNode = makeNode("node-2");

    useCanvasStore.getState().setNodes([node]);
    advanceBurstDebounce();
    useCanvasStore.getState().setEdges([edge]);
    advanceBurstDebounce();
    useCanvasHistoryStore.getState().undo();

    useCanvasStore.getState().setNodes([replacementNode]);
    advanceBurstDebounce();

    expect(useCanvasHistoryStore.getState().future).toEqual([]);
    expect(useCanvasHistoryStore.getState().past).toEqual([
      {
        nodes: [],
        edges: [],
      },
      {
        nodes: [node],
        edges: [],
      },
    ]);
  });

  it("treats undo and redo as no-ops when their history stacks are empty", () => {
    const initialHistory = useCanvasHistoryStore.getState();
    const initialCanvas = useCanvasStore.getState();

    useCanvasHistoryStore.getState().undo();
    useCanvasHistoryStore.getState().redo();

    expect(useCanvasHistoryStore.getState().past).toEqual(initialHistory.past);
    expect(useCanvasHistoryStore.getState().future).toEqual(initialHistory.future);
    expect(useCanvasStore.getState().nodes).toEqual(initialCanvas.nodes);
    expect(useCanvasStore.getState().edges).toEqual(initialCanvas.edges);
  });

  it("does not record undo or redo as new debounced history changes", () => {
    const node = makeNode("node-1");
    const edge = makeEdge("edge-1", "node-1", "node-2");

    useCanvasStore.getState().setNodes([node]);
    advanceBurstDebounce();
    useCanvasStore.getState().setEdges([edge]);
    advanceBurstDebounce();

    useCanvasHistoryStore.getState().undo();

    expect(useCanvasHistoryStore.getState().past).toHaveLength(1);
    expect(useCanvasHistoryStore.getState().future).toHaveLength(1);

    advanceBurstDebounce();

    expect(useCanvasHistoryStore.getState().past).toHaveLength(1);
    expect(useCanvasHistoryStore.getState().future).toHaveLength(1);

    useCanvasHistoryStore.getState().redo();
    advanceBurstDebounce();

    expect(useCanvasHistoryStore.getState().past).toHaveLength(2);
    expect(useCanvasHistoryStore.getState().future).toHaveLength(0);
  });

  it("resetCanvasHistory clears committed history and cancels a pending burst", () => {
    useCanvasStore.getState().setNodes([makeNode("node-1")]);
    vi.advanceTimersByTime(200);

    resetCanvasHistory();

    expect(useCanvasHistoryStore.getState().past).toEqual([]);
    expect(useCanvasHistoryStore.getState().future).toEqual([]);

    advanceBurstDebounce();

    expect(useCanvasHistoryStore.getState().past).toEqual([]);
    expect(useCanvasHistoryStore.getState().future).toEqual([]);
  });

  it("reports canUndo and canRedo from the current history stacks", () => {
    const node = makeNode("node-1");
    const edge = makeEdge("edge-1", "node-1", "node-2");

    expect(useCanvasHistoryStore.getState().canUndo()).toBe(false);
    expect(useCanvasHistoryStore.getState().canRedo()).toBe(false);

    useCanvasStore.getState().setNodes([node]);
    advanceBurstDebounce();

    expect(useCanvasHistoryStore.getState().canUndo()).toBe(true);
    expect(useCanvasHistoryStore.getState().canRedo()).toBe(false);

    useCanvasStore.getState().setEdges([edge]);
    advanceBurstDebounce();
    useCanvasHistoryStore.getState().undo();

    expect(useCanvasHistoryStore.getState().canUndo()).toBe(true);
    expect(useCanvasHistoryStore.getState().canRedo()).toBe(true);

    useCanvasHistoryStore.getState().undo();

    expect(useCanvasHistoryStore.getState().canUndo()).toBe(false);
    expect(useCanvasHistoryStore.getState().canRedo()).toBe(true);
  });
});
