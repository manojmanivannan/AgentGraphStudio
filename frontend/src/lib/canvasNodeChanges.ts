import type { NodeChange } from "@xyflow/react";

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
