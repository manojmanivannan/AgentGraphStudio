/**
 * Pure connection-legality and edge-type derivation rules shared by
 * CanvasView's `isValidConnection` (drag-time gating) and `onConnect`
 * (edge creation). Node types are ReactFlow node `type` strings:
 * "agent" | "tool" | "attachment".
 */

export type CanvasNodeType = "agent" | "tool" | "attachment" | string | undefined;

/** Whether a connection between two node types is legal to draw. */
export function isValidNodeTypeConnection(
  sourceType: CanvasNodeType,
  targetType: CanvasNodeType
): boolean {
  if (sourceType === "agent" && targetType === "tool") return true;
  if (sourceType === "agent" && targetType === "agent") return true;
  // Attachment nodes only wire to agents (produces/consumes, #76/#80).
  // attachment<->attachment and attachment<->tool are always rejected.
  if (sourceType === "agent" && targetType === "attachment") return true;
  if (sourceType === "attachment" && targetType === "agent") return true;
  return false;
}

/** The edge_type to persist for a newly-drawn connection between two node types. */
export function deriveEdgeType(sourceType: CanvasNodeType, targetType: CanvasNodeType): string {
  if (sourceType === "agent" && targetType === "agent") return "handoff";
  if (sourceType === "agent" && targetType === "attachment") return "produces";
  if (sourceType === "attachment" && targetType === "agent") return "consumes";
  return "tool_access";
}
