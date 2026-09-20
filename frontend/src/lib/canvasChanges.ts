import type { EdgeChange, NodeChange } from "@xyflow/react";

/**
 * Filters out ReactFlow `dimensions` changes.
 *
 * ReactFlow emits `dimensions` changes whenever it (re)measures a node — on
 * initial render and again when a node re-renders. They are measurement
 * bookkeeping, not user edits, so routing them through `setNodes` would set
 * `isDirty` and make a freshly-loaded canvas trip the unsaved-changes guard on
 * the very next navigation (e.g. clicking "Agent Chat"). Drop them here before
 * applying changes to the store.
 */
export function withoutMeasurementChanges(changes: NodeChange[]): NodeChange[] {
  return changes.filter((change) => change.type !== "dimensions");
}

/**
 * True when any change represents a real edit to the graph (`add`, `remove`,
 * `replace`) rather than transient geometry/selection bookkeeping (`position`,
 * `select`).
 *
 * Dragging a node emits `position` changes and clicking a node or edge emits
 * `select` changes; neither should trip the unsaved-changes guard. Only
 * structural edits mark the canvas dirty.
 */
export function hasSubstantiveChanges(
  changes: NodeChange[] | EdgeChange[],
): boolean {
  return changes.some(
    (change) =>
      change.type === "add" ||
      change.type === "remove" ||
      change.type === "replace",
  );
}
