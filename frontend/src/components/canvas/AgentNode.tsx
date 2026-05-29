import { memo } from "react";
import { Handle, Position, NodeResizer, type NodeProps } from "@xyflow/react";
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
        relative h-full flex flex-col rounded-xl bg-[var(--color-surface)] border
        shadow-[0_4px_24px_-4px_rgba(0,0,0,0.5)]
        transition-all duration-200
        ${selected
          ? "border-[var(--color-accent)] shadow-[0_0_0_1px_var(--color-accent),0_4px_24px_-4px_rgba(20,184,166,0.2)]"
          : isRouter
          ? "border-[var(--color-agent)]/30"
          : "border-[var(--color-border-default)]"
        }
        ${isActive ? "border-[var(--color-success)] shadow-[0_0_0_1px_var(--color-success),0_0_20px_-4px_rgba(16,185,129,0.3)] animate-pulse" : ""}
      `}
    >
      <NodeResizer
        isVisible={selected}
        minWidth={200}
        minHeight={100}
        handleClassName="!w-2 !h-2 !bg-[var(--color-surface)] !border-[var(--color-accent)] !rounded-sm"
        lineClassName="!border-[var(--color-accent)]/50"
      />
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-[var(--color-text-tertiary)] !w-2 !h-2 !border-2 !border-[var(--color-surface)]"
      />
      <div
        className={`flex items-center gap-2 px-3 py-2.5 rounded-t-xl border-b ${
          isRouter
            ? "bg-[var(--color-agent-surface)] border-[var(--color-agent)]/10"
            : "bg-[var(--color-accent-surface)] border-[var(--color-accent)]/10"
        }`}
      >
        <div
          className={`flex items-center justify-center w-5 h-5 rounded-md ${
            isRouter
              ? "bg-[var(--color-agent-subtle)]"
              : "bg-[var(--color-accent-subtle)]"
          }`}
        >
          {isRouter ? (
            <GitBranch className="w-3 h-3 text-[var(--color-agent)]" />
          ) : (
            <Brain className="w-3 h-3 text-[var(--color-accent)]" />
          )}
        </div>
        <span className="font-semibold text-[13px] text-[var(--color-text-primary)] truncate flex-1">
          {agentData.name}
        </span>
        <span
          className={`text-[10px] px-1.5 py-0.5 rounded-md font-semibold tracking-wide uppercase ${
            isRouter
              ? "bg-[var(--color-agent-subtle)] text-[var(--color-agent)]"
              : "bg-[var(--color-accent-subtle)] text-[var(--color-accent)]"
          }`}
        >
          {isRouter ? "Router" : "Worker"}
        </span>
      </div>
      <div className="px-3 py-2.5 flex-1 overflow-hidden">
        {agentData.role && (
          <p className="text-[12px] text-[var(--color-text-secondary)] line-clamp-2 leading-relaxed">
            {agentData.role}
          </p>
        )}
        {agentData.instructions && (
          <p className="text-[11px] text-[var(--color-text-tertiary)] mt-1.5 line-clamp-4 leading-relaxed font-[var(--font-mono)]">
            {agentData.instructions}
          </p>
        )}
        {!agentData.role && !agentData.instructions && (
          <p className="text-[11px] text-[var(--color-text-tertiary)] italic">
            Configure agent properties
          </p>
        )}
      </div>
      <Handle
        type="source"
        position={Position.Bottom}
        className={`!w-2 !h-2 !border-2 !border-[var(--color-surface)] ${
          isRouter ? "!bg-[var(--color-agent)]" : "!bg-[var(--color-accent)]"
        }`}
      />
    </div>
  );
}

export const AgentNode = memo(AgentNodeComponent);