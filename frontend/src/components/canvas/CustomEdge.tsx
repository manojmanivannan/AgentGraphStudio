import { useCallback } from "react";
import type { EdgeProps } from "@xyflow/react";
import { BaseEdge, EdgeLabelRenderer, getBezierPath, useReactFlow } from "@xyflow/react";
import { X } from "lucide-react";

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
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const { deleteElements } = useReactFlow();

  const handleDelete = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      e.preventDefault();
      deleteElements({ edges: [{ id }] });
    },
    [deleteElements, id]
  );

  const isHandoff = data?.edgeType === "handoff";

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          strokeWidth: 2,
          strokeDasharray: isHandoff ? "6 4" : undefined,
          stroke: isHandoff ? "var(--color-agent)" : "var(--color-text-tertiary)",
          opacity: isHandoff ? 0.7 : 0.4,
        }}
        markerEnd={markerEnd}
      />
      <EdgeLabelRenderer>
        <div
          className="nodrag nopan absolute group"
          style={{
            left: labelX,
            top: labelY,
            width: 28,
            height: 28,
            transform: "translate(-50%, -50%)",
            pointerEvents: "all",
          }}
        >
          <button
            className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2
              w-5 h-5 rounded-md bg-[var(--color-danger)] text-white flex items-center justify-center
              opacity-0 group-hover:opacity-100 transition-all duration-200
              shadow-[0_2px_8px_-2px_rgba(239,68,68,0.4)] hover:bg-[var(--color-danger)]/90 z-10
              scale-75 group-hover:scale-100"
            style={{ pointerEvents: "all" }}
            onMouseDown={handleDelete}
            title="Delete edge"
          >
            <X className="w-3 h-3" />
          </button>
        </div>
      </EdgeLabelRenderer>
    </>
  );
}