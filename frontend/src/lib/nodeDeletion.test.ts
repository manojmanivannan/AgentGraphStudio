import { beforeEach, describe, expect, it, vi } from "vitest";
import { useCanvasStore } from "@/store/canvasStore";
import { deleteNodeWithConfirm, deleteSelectedNodesWithConfirm } from "./nodeDeletion";

const confirmMock = vi.hoisted(() => vi.fn());
vi.mock("@/store/confirmStore", () => ({
  confirm: confirmMock,
}));

beforeEach(() => {
  useCanvasStore.getState().reset();
  confirmMock.mockReset();
});

describe("deleteNodeWithConfirm", () => {
  it("does nothing if the node does not exist", async () => {
    confirmMock.mockResolvedValue(true);
    const result = await deleteNodeWithConfirm("missing");
    expect(result).toBe(false);
    expect(confirmMock).not.toHaveBeenCalled();
  });

  it("asks for confirmation and does not delete when cancelled", async () => {
    confirmMock.mockResolvedValue(false);
    useCanvasStore.getState().setNodes([
      { id: "n1", type: "agent", position: { x: 0, y: 0 }, data: { name: "Agent 1" } } as any,
    ]);

    const result = await deleteNodeWithConfirm("n1");

    expect(result).toBe(false);
    expect(confirmMock).toHaveBeenCalledWith(
      expect.objectContaining({ danger: true, description: expect.stringContaining("Agent 1") })
    );
    expect(useCanvasStore.getState().nodes).toHaveLength(1);
  });

  it("deletes the node and its connected edges when confirmed", async () => {
    confirmMock.mockResolvedValue(true);
    useCanvasStore.getState().setNodes([
      { id: "n1", type: "agent", position: { x: 0, y: 0 }, data: { name: "Agent 1" } } as any,
      { id: "n2", type: "tool", position: { x: 0, y: 0 }, data: { name: "Tool 1" } } as any,
    ]);
    useCanvasStore.getState().setEdges([
      { id: "e1", source: "n1", target: "n2" } as any,
      { id: "e2", source: "n2", target: "n2" } as any,
    ]);
    useCanvasStore.getState().selectNode("n1");
    useCanvasStore.getState().setActiveNodeId("n1");

    const result = await deleteNodeWithConfirm("n1");

    expect(result).toBe(true);
    expect(useCanvasStore.getState().nodes.map((n) => n.id)).toEqual(["n2"]);
    expect(useCanvasStore.getState().edges.map((e) => e.id)).toEqual(["e2"]);
    expect(useCanvasStore.getState().selectedNodeId).toBeNull();
    expect(useCanvasStore.getState().activeNodeId).toBeNull();
  });
});

describe("deleteSelectedNodesWithConfirm", () => {
  it("does nothing if no nodes are selected", async () => {
    confirmMock.mockResolvedValue(true);
    useCanvasStore.getState().setNodes([
      { id: "n1", type: "agent", position: { x: 0, y: 0 }, data: { name: "Agent 1" }, selected: false } as any,
    ]);

    const result = await deleteSelectedNodesWithConfirm();

    expect(result).toBe(false);
    expect(confirmMock).not.toHaveBeenCalled();
    expect(useCanvasStore.getState().nodes).toHaveLength(1);
  });

  it("deletes all selected nodes and their edges when confirmed", async () => {
    confirmMock.mockResolvedValue(true);
    useCanvasStore.getState().setNodes([
      { id: "n1", type: "agent", position: { x: 0, y: 0 }, data: { name: "Agent 1" }, selected: true } as any,
      { id: "n2", type: "tool", position: { x: 0, y: 0 }, data: { name: "Tool 1" }, selected: true } as any,
      { id: "n3", type: "tool", position: { x: 0, y: 0 }, data: { name: "Tool 2" }, selected: false } as any,
    ]);
    useCanvasStore.getState().setEdges([
      { id: "e1", source: "n1", target: "n2" } as any,
      { id: "e2", source: "n2", target: "n3" } as any,
    ]);

    const result = await deleteSelectedNodesWithConfirm();

    expect(result).toBe(true);
    expect(confirmMock).toHaveBeenCalledWith(
      expect.objectContaining({ title: "Delete 2 nodes" })
    );
    expect(useCanvasStore.getState().nodes.map((n) => n.id)).toEqual(["n3"]);
    expect(useCanvasStore.getState().edges).toHaveLength(0);
  });

  it("leaves nodes untouched when the confirmation is cancelled", async () => {
    confirmMock.mockResolvedValue(false);
    useCanvasStore.getState().setNodes([
      { id: "n1", type: "agent", position: { x: 0, y: 0 }, data: { name: "Agent 1" }, selected: true } as any,
    ]);

    const result = await deleteSelectedNodesWithConfirm();

    expect(result).toBe(false);
    expect(useCanvasStore.getState().nodes).toHaveLength(1);
  });
});
