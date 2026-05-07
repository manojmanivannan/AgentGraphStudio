import type { EdgeProps } from "@xyflow/react";
import { BaseEdge, getBezierPath } from "@xyflow/react";

export function CustomEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  markerEnd,
}: EdgeProps) {
  const [edgePath] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const isHandoff = data?.edgeType === "handoff";

  return (
    <BaseEdge
      id={id}
      path={edgePath}
      style={{
        strokeWidth: 2,
        strokeDasharray: isHandoff ? "6 4" : undefined,
        stroke: isHandoff ? "#a78bfa" : "#6b7280",
      }}
      markerEnd={markerEnd}
    />
  );
}
