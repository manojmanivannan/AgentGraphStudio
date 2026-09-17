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

/**
 * Named ReactFlow handle ids. AgentNode exposes several distinct handles per
 * side so handoff (agent<->agent), tool_access (agent->tool), and
 * produces/consumes (agent<->attachment) connections each get their own fixed
 * anchor point instead of all converging on the same center dot (#-offset-handles).
 * Handoff stays centered top/bottom; tool anchors sit left of center;
 * attachment anchors sit right of center.
 */
export const HANDLE_IDS = {
  agentHandoffTarget: "agent-in",
  agentHandoffSource: "agent-out",
  agentToolSource: "tool-out",
  toolTarget: "tool-in",
  agentAttachmentTarget: "attachment-in",
  agentAttachmentSource: "attachment-out",
  attachmentProducesTarget: "attachment-target",
  attachmentConsumesSource: "attachment-source",
} as const;

/** Resolves the (sourceHandle, targetHandle) pair to use for a given persisted edge_type. */
export function getEdgeHandles(edgeType: string): { sourceHandle: string; targetHandle: string } {
  switch (edgeType) {
    case "handoff":
      return { sourceHandle: HANDLE_IDS.agentHandoffSource, targetHandle: HANDLE_IDS.agentHandoffTarget };
    case "produces":
      return { sourceHandle: HANDLE_IDS.agentAttachmentSource, targetHandle: HANDLE_IDS.attachmentProducesTarget };
    case "consumes":
      return { sourceHandle: HANDLE_IDS.attachmentConsumesSource, targetHandle: HANDLE_IDS.agentAttachmentTarget };
    case "tool_access":
    default:
      return { sourceHandle: HANDLE_IDS.agentToolSource, targetHandle: HANDLE_IDS.toolTarget };
  }
}
