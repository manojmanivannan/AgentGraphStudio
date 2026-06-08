import { beforeEach, describe, expect, it } from "vitest";
import { useCanvasStore } from "./canvasStore";

const store = () => useCanvasStore.getState();

beforeEach(() => {
  store().reset();
});

describe("canvasStore", () => {
  describe("initial state", () => {
    it("has expected defaults", () => {
      expect(store().canvasId).toBeNull();
      expect(store().canvasName).toBe("Untitled Canvas");
      expect(store().nodes).toEqual([]);
      expect(store().edges).toEqual([]);
      expect(store().selectedNodeId).toBeNull();
      expect(store().activeNodeId).toBeNull();
      expect(store().chatOpen).toBe(false);
      expect(store().saveStatus).toBe("idle");
    });
  });

  describe("setCanvas", () => {
    it("sets id and name", () => {
      store().setCanvas("id-1", "My Canvas");
      expect(store().canvasId).toBe("id-1");
      expect(store().canvasName).toBe("My Canvas");
    });
  });

  describe("setName", () => {
    it("updates only the name", () => {
      store().setCanvas("id-1", "Original");
      store().setName("Renamed");
      expect(store().canvasId).toBe("id-1");
      expect(store().canvasName).toBe("Renamed");
    });
  });

  describe("setNodes", () => {
    it("replaces nodes array", () => {
      const nodes = [{ id: "n1", type: "agent", position: { x: 0, y: 0 }, data: {} }] as any;
      store().setNodes(nodes);
      expect(store().nodes).toEqual(nodes);
    });
  });

  describe("setEdges", () => {
    it("replaces edges array", () => {
      const edges = [{ id: "e1", source: "n1", target: "n2" }] as any;
      store().setEdges(edges);
      expect(store().edges).toEqual(edges);
    });
  });

  describe("selectNode", () => {
    it("sets selectedNodeId when id is non-null", () => {
      store().selectNode("n1");
      expect(store().selectedNodeId).toBe("n1");
    });

    it("clears selectedNodeId when id is null", () => {
      store().selectNode("n1");
      store().selectNode(null);
      expect(store().selectedNodeId).toBeNull();
    });
  });

  describe("setActiveNodeId", () => {
    it("sets the active node for execution highlighting", () => {
      store().setActiveNodeId("n2");
      expect(store().activeNodeId).toBe("n2");
    });

    it("clears the active node when set to null", () => {
      store().setActiveNodeId("n2");
      store().setActiveNodeId(null);
      expect(store().activeNodeId).toBeNull();
    });
  });

  describe("toggleChat", () => {
    it("toggles the chat panel open/closed", () => {
      expect(store().chatOpen).toBe(false);
      store().toggleChat();
      expect(store().chatOpen).toBe(true);
      store().toggleChat();
      expect(store().chatOpen).toBe(false);
    });
  });

  describe("setSaveStatus", () => {
    it("updates the save status", () => {
      store().setSaveStatus("saving");
      expect(store().saveStatus).toBe("saving");
      store().setSaveStatus("saved");
      expect(store().saveStatus).toBe("saved");
      store().setSaveStatus("error");
      expect(store().saveStatus).toBe("error");
    });
  });

  describe("toggleObservability", () => {
    it("toggles the observability panel open/closed", () => {
      expect(store().observabilityOpen).toBe(false);
      store().toggleObservability();
      expect(store().observabilityOpen).toBe(true);
      store().toggleObservability();
      expect(store().observabilityOpen).toBe(false);
    });
  });

  describe("setViewport", () => {
    it("updates the viewport zoom and coordinates", () => {
      const newViewport = { x: 10, y: 20, zoom: 1.5 };
      store().setViewport(newViewport);
      expect(store().viewport).toEqual(newViewport);
    });
  });

  describe("reset", () => {
    it("restores all state to defaults", () => {
      store().setCanvas("id-99", "Some Canvas");
      store().setNodes([{ id: "n1", type: "agent", position: { x: 0, y: 0 }, data: {} }] as any);
      store().selectNode("n1");
      store().setActiveNodeId("n1");
      store().toggleChat();
      store().toggleObservability();
      store().setSaveStatus("saving");
      store().setViewport({ x: 10, y: 20, zoom: 1.5 });

      store().reset();

      expect(store().canvasId).toBeNull();
      expect(store().canvasName).toBe("Untitled Canvas");
      expect(store().nodes).toEqual([]);
      expect(store().edges).toEqual([]);
      expect(store().selectedNodeId).toBeNull();
      expect(store().activeNodeId).toBeNull();
      expect(store().chatOpen).toBe(false);
      expect(store().observabilityOpen).toBe(false);
      expect(store().saveStatus).toBe("idle");
      expect(store().viewport).toEqual({ x: 0, y: 0, zoom: 1 });
    });
  });
});