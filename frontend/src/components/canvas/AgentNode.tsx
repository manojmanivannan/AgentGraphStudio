import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Brain, GitBranch } from "lucide-react";
import type { AgentNodeData } from "@/types";
import { useCanvasStore } from "@/store/canvasStore";

function AgentNodeComponent({ id, data, selected }: NodeProps) {
  const agentData = data as unknown as AgentNodeData;
  const activeNodeId = useCanvasStore((s) => s.activeNodeId);
  const isRouter = agentData.agentType === "router";
  const isActive = activeNodeId === agentData.id;

  return (
    <div
      data-testid="agent-node"
      data-node-id={id}
      data-agent-type={agentData.agentType}
      className={`
        relative min-w-[200px] rounded-lg border-2 bg-white shadow-md transition-all duration-300
        ${selected ? "border-blue-500 ring-2 ring-blue-200" : isRouter ? "border-purple-300" : "border-gray-200"}
        ${isActive ? "border-green-400 ring-2 ring-green-200 animate-pulse" : ""}
      `}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-gray-400 !w-2.5 !h-2.5"
      />
      <div
        className={`flex items-center gap-2 px-3 py-2 rounded-t-lg border-b border-gray-100 ${
          isRouter
            ? "bg-gradient-to-r from-purple-50 to-pink-50"
            : "bg-gradient-to-r from-indigo-50 to-purple-50"
        }`}
      >
        {isRouter ? (
          <GitBranch className="w-4 h-4 text-purple-500" />
        ) : (
          <Brain className="w-4 h-4 text-indigo-500" />
        )}
        <span className="font-semibold text-sm text-gray-800 truncate">
          {agentData.name}
        </span>
        <span
          className={`ml-auto text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
            isRouter
              ? "bg-purple-100 text-purple-600"
              : "bg-indigo-100 text-indigo-600"
          }`}
        >
          {isRouter ? "Router" : "Worker"}
        </span>
      </div>
      <div className="px-3 py-2">
        {agentData.role && (
          <p className="text-xs text-gray-500 line-clamp-2">
            {agentData.role}
          </p>
        )}
        {agentData.instructions && (
          <p className="text-xs text-gray-400 mt-1 line-clamp-2">
            {agentData.instructions}
          </p>
        )}
        {!agentData.role && !agentData.instructions && (
          <p className="text-xs text-gray-300 italic">
            Configure agent properties
          </p>
        )}
      </div>
      <Handle
        type="source"
        position={Position.Bottom}
        className={`!w-2.5 !h-2.5 ${isRouter ? "!bg-purple-500" : "!bg-indigo-500"}`}
      />
    </div>
  );
}

export const AgentNode = memo(AgentNodeComponent);
