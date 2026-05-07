import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Brain } from "lucide-react";
import type { AgentNodeData } from "@/types";
import { useCanvasStore } from "@/store/canvasStore";

function AgentNodeComponent({ id, data, selected }: NodeProps) {
  const agentData = data as unknown as AgentNodeData;
  const executionStatus = useCanvasStore((s) => s.executionStatus);
  const executionEvents = useCanvasStore((s) => s.executionEvents);

  const isActive = executionStatus === "running" && executionEvents.some(
    (e) => e.type === "agent_start" && e.agent === agentData.name
  );
  const latestEvent = [...executionEvents].reverse().find(
    (e) => e.type === "agent_start" && e.agent === agentData.name
  );

  const latestDone = [...executionEvents].reverse().find(
    (e) => (e.type === "run_complete" || e.type === "error" || (e.type === "handoff" && e.from === agentData.name))
  );

  const isCurrentlyActive = isActive && !latestDone;

  return (
    <div
      className={`
        relative min-w-[200px] rounded-lg border-2 bg-white shadow-md transition-all duration-300
        ${selected ? "border-blue-500 ring-2 ring-blue-200" : "border-gray-200"}
        ${isCurrentlyActive ? "border-green-400 ring-2 ring-green-200 animate-pulse" : ""}
      `}
    >
      <Handle type="target" position={Position.Top} className="!bg-gray-400 !w-2.5 !h-2.5" />
      <div className="flex items-center gap-2 px-3 py-2 bg-gradient-to-r from-indigo-50 to-purple-50 rounded-t-lg border-b border-gray-100">
        <Brain className="w-4 h-4 text-indigo-500" />
        <span className="font-semibold text-sm text-gray-800 truncate">{agentData.name}</span>
        {agentData.modelName && (
          <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded-full bg-indigo-100 text-indigo-600 font-medium">
            {agentData.modelName.split(":").pop()}
          </span>
        )}
      </div>
      <div className="px-3 py-2">
        {agentData.role && (
          <p className="text-xs text-gray-500 line-clamp-2">{agentData.role}</p>
        )}
        {agentData.instructions && (
          <p className="text-xs text-gray-400 mt-1 line-clamp-2">{agentData.instructions}</p>
        )}
        {!agentData.role && !agentData.instructions && (
          <p className="text-xs text-gray-300 italic">Configure agent properties</p>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-indigo-500 !w-2.5 !h-2.5" />
    </div>
  );
}

export const AgentNode = memo(AgentNodeComponent);
