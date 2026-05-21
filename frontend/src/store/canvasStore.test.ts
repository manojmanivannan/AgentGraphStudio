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
      expect(store().propertiesOpen).toBe(false);
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
    it("sets selectedNodeId and opens properties panel when id is non-null", () => {
      store().selectNode("n1");
      expect(store().selectedNodeId).toBe("n1");
      expect(store().propertiesOpen).toBe(true);
    });

    it("clears selectedNodeId and closes properties panel when id is null", () => {
      store().selectNode("n1");
      store().selectNode(null);
      expect(store().selectedNodeId).toBeNull();
      expect(store().propertiesOpen).toBe(false);
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

  describe("toggleProperties", () => {
    it("toggles the properties panel open/closed", () => {
      expect(store().propertiesOpen).toBe(false);
      store().toggleProperties();
      expect(store().propertiesOpen).toBe(true);
      store().toggleProperties();
      expect(store().propertiesOpen).toBe(false);
    });
  });

  describe("reset", () => {
    it("restores all state to defaults", () => {
      store().setCanvas("id-99", "Some Canvas");
      store().setNodes([{ id: "n1", type: "agent", position: { x: 0, y: 0 }, data: {} }] as any);
      store().selectNode("n1");
      store().setActiveNodeId("n1");

      store().reset();

      expect(store().canvasId).toBeNull();
      expect(store().canvasName).toBe("Untitled Canvas");
      expect(store().nodes).toEqual([]);
      expect(store().edges).toEqual([]);
      expect(store().selectedNodeId).toBeNull();
      expect(store().activeNodeId).toBeNull();
      expect(store().propertiesOpen).toBe(false);
    });
  });
});
