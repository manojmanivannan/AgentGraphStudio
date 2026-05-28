import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Wrench } from "lucide-react";
import type { ToolNodeData } from "@/types";
import { useCanvasStore } from "@/store/canvasStore";

function ToolNodeComponent({ id, data, selected }: NodeProps) {
  const toolData = data as unknown as ToolNodeData;
  const activeNodeId = useCanvasStore((s) => s.activeNodeId);
  const isActive = activeNodeId === toolData.id;

  const codePreview =
    toolData.code
      ?.split("\n")
      .slice(0, 3)
      .join("\n") || "";

  return (
    <div
      data-testid="tool-node"
      data-node-id={id}
      className={`
        relative min-w-[180px] rounded-lg border-2 bg-white shadow-md
        ${selected ? "border-blue-500 ring-2 ring-blue-200" : "border-gray-200"}
        ${isActive ? "border-green-400 ring-2 ring-green-200 animate-pulse" : ""}
      `}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-gray-400 !w-2.5 !h-2.5"
      />
      <div className="flex items-center gap-2 px-3 py-2 bg-gradient-to-r from-amber-50 to-orange-50 rounded-t-lg border-b border-gray-100">
        <Wrench className="w-4 h-4 text-amber-500" />
        <span className="font-semibold text-sm text-gray-800 truncate">
          {toolData.name}
        </span>
      </div>
      <div className="px-3 py-2">
        {codePreview ? (
          <pre className="text-[10px] text-gray-500 font-mono leading-relaxed overflow-hidden">
            {codePreview}
          </pre>
        ) : (
          <p className="text-xs text-gray-300 italic">Write Python code</p>
        )}
      </div>
      <Handle
        type="source"
        position={Position.Bottom}
        className="!bg-amber-500 !w-2.5 !h-2.5"
      />
    </div>
  );
}

export const ToolNode = memo(ToolNodeComponent);
