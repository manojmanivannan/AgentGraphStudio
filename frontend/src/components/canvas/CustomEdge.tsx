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
          stroke: isHandoff ? "#a78bfa" : "#6b7280",
        }}
        markerEnd={markerEnd}
      />
      <EdgeLabelRenderer>
        <div
          className="nodrag nopan absolute group"
          style={{
            left: labelX,
            top: labelY,
            width: 40,
            height: 40,
            transform: "translate(-50%, -50%)",
            pointerEvents: "all",
          }}
        >
          <button
            className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2
              w-5 h-5 rounded-full bg-red-500 text-white flex items-center justify-center
              opacity-0 group-hover:opacity-100 transition-opacity duration-200
              shadow-sm hover:bg-red-600 z-10"
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
