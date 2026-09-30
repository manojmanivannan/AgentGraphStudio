import type { Node } from "@xyflow/react";

/** Minimum empty space kept between two node boxes, in flow units. */
export const NODE_GAP = 16;

/** Used when ReactFlow has not measured a node yet (e.g. first render). */
const FALLBACK_WIDTH = 200;
const FALLBACK_HEIGHT = 110;

/** Safety valve: the push-out loop can oscillate between two neighbours. */
const MAX_PASSES = 32;

/** Ring-search fallback granularity, in flow units. */
const SEARCH_STEP = 24;
const SEARCH_RINGS = 80;
const SEARCH_ANGLES = 24;

interface Rect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

interface Point {
  x: number;
  y: number;
}

export interface Size {
  width: number;
  height: number;
}

export interface CollisionOptions {
  gap?: number;
  /**
   * Real rendered sizes, keyed by node id. Nodes held in the canvas store do
   * not carry `measured` (ReactFlow `dimensions` changes are filtered out
   * before they reach the store), so without this every node would be assumed
   * to be the same fallback size and boxes of other sizes would still overlap.
   */
  sizes?: Map<string, Size>;
}

function sizeOf(node: Node, sizes?: Map<string, Size>): Size {
  const measured = sizes?.get(node.id) ?? node.measured;
  return {
    width: measured?.width ?? node.width ?? FALLBACK_WIDTH,
    height: measured?.height ?? node.height ?? FALLBACK_HEIGHT,
  };
}

function rectOf(
  node: Node,
  position: Point,
  gap: number,
  sizes?: Map<string, Size>,
): Rect {
  const { width, height } = sizeOf(node, sizes);
  const pad = gap / 2;
  return {
    left: position.x - pad,
    top: position.y - pad,
    right: position.x + width + pad,
    bottom: position.y + height + pad,
  };
}

function overlapOf(a: Rect, b: Rect): Point | null {
  const x = Math.min(a.right, b.right) - Math.max(a.left, b.left);
  const y = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
  if (x <= 0 || y <= 0) return null;
  return { x, y };
}

function firstCollision(
  rect: Rect,
  obstacles: Rect[],
): { rect: Rect; overlap: Point } | null {
  for (const obstacle of obstacles) {
    const overlap = overlapOf(rect, obstacle);
    if (overlap) return { rect: obstacle, overlap };
  }
  return null;
}

/**
 * Slides the node out of whatever it sits on, one collision at a time, along
 * the axis it is least buried in. Can oscillate between two neighbours on a
 * crowded canvas, hence the pass cap and the ring-search fallback.
 */
function pushOut(
  node: Node,
  start: Point,
  obstacles: Rect[],
  gap: number,
  sizes?: Map<string, Size>,
): Point {
  const position = { ...start };

  for (let pass = 0; pass < MAX_PASSES; pass++) {
    const rect = rectOf(node, position, gap, sizes);
    const collision = firstCollision(rect, obstacles);
    if (!collision) break;

    const { rect: other, overlap } = collision;
    if (overlap.x <= overlap.y) {
      const draggedCenter = (rect.left + rect.right) / 2;
      const otherCenter = (other.left + other.right) / 2;
      position.x += draggedCenter < otherCenter ? -overlap.x : overlap.x;
    } else {
      const draggedCenter = (rect.top + rect.bottom) / 2;
      const otherCenter = (other.top + other.bottom) / 2;
      position.y += draggedCenter < otherCenter ? -overlap.y : overlap.y;
    }
  }

  return position;
}

/** Scans outward from the drop point in widening rings for a free spot. */
function searchFreePosition(
  node: Node,
  origin: Point,
  obstacles: Rect[],
  gap: number,
  sizes?: Map<string, Size>,
): Point | null {
  for (let ring = 1; ring <= SEARCH_RINGS; ring++) {
    const radius = ring * SEARCH_STEP;
    for (let step = 0; step < SEARCH_ANGLES; step++) {
      const angle = (step / SEARCH_ANGLES) * 2 * Math.PI;
      const candidate = {
        x: Math.round(origin.x + Math.cos(angle) * radius),
        y: Math.round(origin.y + Math.sin(angle) * radius),
      };
      if (!firstCollision(rectOf(node, candidate, gap, sizes), obstacles)) {
        return candidate;
      }
    }
  }
  return null;
}

/**
 * Returns a position for `nodeId` that does not overlap any other node.
 *
 * Returns the node's current position when it is already clear, so callers can
 * cheaply detect "nothing to do".
 */
export function resolveNodePosition(
  nodes: Node[],
  nodeId: string,
  options: CollisionOptions = {},
): Point {
  const { gap = NODE_GAP, sizes } = options;
  const dragged = nodes.find((n) => n.id === nodeId);
  if (!dragged) return { x: 0, y: 0 };

  const obstacles = nodes
    .filter((n) => n.id !== nodeId && !n.hidden)
    .map((n) => rectOf(n, n.position, gap, sizes));

  const origin = { ...dragged.position };
  if (!firstCollision(rectOf(dragged, origin, gap, sizes), obstacles)) return origin;

  const pushed = pushOut(dragged, origin, obstacles, gap, sizes);
  if (!firstCollision(rectOf(dragged, pushed, gap, sizes), obstacles)) return pushed;

  return searchFreePosition(dragged, origin, obstacles, gap, sizes) ?? pushed;
}

/**
 * Returns `nodes` with `nodeId` moved to the nearest non-overlapping spot, or
 * the original array reference when it already sits clear of every other node.
 */
export function resolveNodeOverlap(
  nodes: Node[],
  nodeId: string,
  options: CollisionOptions = {},
): Node[] {
  const dragged = nodes.find((n) => n.id === nodeId);
  if (!dragged) return nodes;

  const resolved = resolveNodePosition(nodes, nodeId, options);
  if (resolved.x === dragged.position.x && resolved.y === dragged.position.y) {
    return nodes;
  }

  return nodes.map((node) =>
    node.id === nodeId ? { ...node, position: resolved } : node,
  );
}
