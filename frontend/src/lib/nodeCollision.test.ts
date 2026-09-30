import { describe, it, expect } from "vitest";
import type { Node } from "@xyflow/react";
import {
  NODE_GAP,
  resolveNodeOverlap,
  resolveNodePosition,
  type Size,
} from "./nodeCollision";

function node(id: string, x: number, y: number, size?: Size): Node {
  return {
    id,
    type: "agent",
    position: { x, y },
    data: {},
    measured: size ?? { width: 200, height: 100 },
  };
}

function bare(id: string, x: number, y: number, type = "agent"): Node {
  return { id, type, position: { x, y }, data: {} };
}

function overlaps(
  a: Node,
  b: Node,
  sizes?: Map<string, Size>,
  gap = NODE_GAP,
): boolean {
  const sizeOf = (n: Node): Size => {
    const size = sizes?.get(n.id) ?? n.measured;
    return { width: size?.width ?? 0, height: size?.height ?? 0 };
  };
  const sa = sizeOf(a);
  const sb = sizeOf(b);
  return (
    a.position.x < b.position.x + sb.width + gap &&
    a.position.x + sa.width + gap > b.position.x &&
    a.position.y < b.position.y + sb.height + gap &&
    a.position.y + sa.height + gap > b.position.y
  );
}

describe("resolveNodePosition", () => {
  it("leaves a node that overlaps nothing where it is", () => {
    const nodes = [node("a", 0, 0), node("b", 500, 500)];
    expect(resolveNodePosition(nodes, "a")).toEqual({ x: 0, y: 0 });
  });

  it("pushes horizontally when the horizontal overlap is shallower", () => {
    const nodes = [node("a", 190, 0), node("b", 0, 0)];
    const resolved = resolveNodePosition(nodes, "a");
    expect(resolved.y).toBe(0);
    expect(resolved.x).toBe(200 + NODE_GAP);
  });

  it("pushes vertically when the vertical overlap is shallower", () => {
    const nodes = [node("a", 0, 95), node("b", 0, 0)];
    const resolved = resolveNodePosition(nodes, "a");
    expect(resolved.x).toBe(0);
    expect(resolved.y).toBe(100 + NODE_GAP);
  });

  it("pushes toward the side the node is already leaning to", () => {
    const nodes = [node("a", -190, 0), node("b", 0, 0)];
    const resolved = resolveNodePosition(nodes, "a");
    expect(resolved.x).toBe(-(200 + NODE_GAP));
  });

  it("keeps resolving until the node is clear of every neighbour", () => {
    const nodes = [
      node("dragged", 10, 10),
      node("b", 0, 0),
      node("c", 216, 0),
      node("d", 432, 0),
    ];
    const resolved = resolveNodePosition(nodes, "dragged");
    const moved = { ...nodes[0], position: resolved };
    for (const other of nodes.slice(1)) {
      expect(overlaps(moved, other)).toBe(false);
    }
  });

  it("ignores hidden nodes", () => {
    const hidden = { ...node("b", 0, 0), hidden: true };
    const nodes = [node("a", 10, 10), hidden];
    expect(resolveNodePosition(nodes, "a")).toEqual({ x: 10, y: 10 });
  });

  it("finds a free spot on a crowded canvas where sliding out oscillates", () => {
    const grid: Node[] = [];
    for (let row = 0; row < 4; row++) {
      for (let col = 0; col < 4; col++) {
        grid.push(node(`n${row}-${col}`, col * 210, row * 105));
      }
    }
    const nodes = [node("dragged", 315, 160), ...grid];

    const resolved = resolveNodePosition(nodes, "dragged");
    const moved = { ...nodes[0], position: resolved };
    for (const other of grid) {
      expect(overlaps(moved, other)).toBe(false);
    }
  });

  // Canvas store nodes carry no `measured`, so a caller-supplied size map is
  // the only way differing node sizes are respected.
  it("uses caller-supplied sizes for nodes that carry no measurements", () => {
    const sizes = new Map<string, Size>([
      ["small", { width: 90, height: 40 }],
      ["big", { width: 380, height: 260 }],
    ]);
    const nodes = [bare("small", 100, 100), bare("big", 0, 0)];

    const resolved = resolveNodePosition(nodes, "small", { sizes });
    const moved = { ...nodes[0], position: resolved };

    expect(overlaps(moved, nodes[1], sizes)).toBe(false);
    expect(resolved).not.toEqual({ x: 100, y: 100 });
  });

  it("clears a small node dropped on a large one among differently sized nodes", () => {
    const sizes = new Map<string, Size>([
      ["tool", { width: 98, height: 40 }],
      ["router", { width: 380, height: 240 }],
      ["worker", { width: 300, height: 180 }],
      ["attachment", { width: 150, height: 70 }],
    ]);
    const nodes = [
      bare("tool", 120, 90, "tool"),
      bare("router", 0, 0),
      bare("worker", 420, 0),
      bare("attachment", 0, 300, "attachment"),
    ];

    const resolved = resolveNodePosition(nodes, "tool", { sizes });
    const moved = { ...nodes[0], position: resolved };
    for (const other of nodes.slice(1)) {
      expect(overlaps(moved, other, sizes)).toBe(false);
    }
  });

  it("honours a custom gap", () => {
    const nodes = [node("a", 190, 0), node("b", 0, 0)];
    expect(resolveNodePosition(nodes, "a", { gap: 40 }).x).toBe(240);
  });
});

describe("resolveNodeOverlap", () => {
  it("returns the same array reference when nothing moved", () => {
    const nodes = [node("a", 0, 0), node("b", 500, 500)];
    expect(resolveNodeOverlap(nodes, "a")).toBe(nodes);
  });

  it("returns a new array with only the dragged node repositioned", () => {
    const nodes = [node("a", 10, 0), node("b", 0, 0)];
    const next = resolveNodeOverlap(nodes, "a");

    expect(next).not.toBe(nodes);
    expect(next[1]).toBe(nodes[1]);
    expect(next[0].position).not.toEqual(nodes[0].position);
    expect(overlaps(next[0], next[1])).toBe(false);
  });

  it("returns the original array for an unknown node id", () => {
    const nodes = [node("a", 0, 0)];
    expect(resolveNodeOverlap(nodes, "missing")).toBe(nodes);
  });
});
