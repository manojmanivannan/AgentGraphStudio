import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Wrench, Settings } from "lucide-react";
import type { ToolNodeData } from "@/types";
import { useCanvasStore } from "@/store/canvasStore";

function ToolNodeComponent({ id, data, selected }: NodeProps) {
  const toolData = data as unknown as ToolNodeData;
  const activeNodeId = useCanvasStore((s) => s.activeNodeId);
  const selectNode = useCanvasStore((s) => s.selectNode);
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
        relative min-w-[180px] rounded-xl bg-[var(--color-surface)] border
        shadow-[0_4px_24px_-4px_rgba(0,0,0,0.5)]
        transition-all duration-200
        ${selected
          ? "border-[var(--color-secondary)] shadow-[0_0_0_1px_var(--color-secondary),0_4px_24px_-4px_rgba(245,158,11,0.2)]"
          : "border-[var(--color-border-default)]"
        }
        ${isActive ? "border-[var(--color-danger)] glow-active-pulse" : ""}
      `}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-[var(--color-text-tertiary)] !w-2 !h-2 !border-2 !border-[var(--color-surface)]"
      />
      <div className="flex items-center gap-2 px-3 py-2.5 bg-[var(--color-secondary-surface)] rounded-t-xl border-b border-[var(--color-secondary)]/10">
        <div className="flex items-center justify-center w-5 h-5 rounded-md bg-[var(--color-secondary-subtle)]">
          <Wrench className="w-3 h-3 text-[var(--color-secondary)]" />
        </div>
        <span className="font-semibold text-[13px] text-[var(--color-text-primary)] truncate flex-1">
          {toolData.name}
        </span>
        <span className="text-[10px] px-1.5 py-0.5 rounded-md font-semibold tracking-wide uppercase bg-[var(--color-secondary-subtle)] text-[var(--color-secondary)]">
          Tool
        </span>
        <button
          onPointerDown={(e) => e.nativeEvent.stopImmediatePropagation()}
          onClick={(e) => {
            e.stopPropagation();
            selectNode(id);
          }}
          className="p-1 text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] rounded-md hover:bg-[var(--color-elevated)] transition-all duration-150"
          title="Settings"
        >
          <Settings className="w-3.5 h-3.5" />
        </button>
      </div>
      <div className="px-3 py-2.5">
        {codePreview ? (
          <pre className="text-[10px] text-[var(--color-text-tertiary)] font-[var(--font-mono)] leading-relaxed overflow-hidden">
            {codePreview}
          </pre>
        ) : (
          <p className="text-[11px] text-[var(--color-text-tertiary)] italic">Write Python code</p>
        )}
      </div>
      <Handle
        type="source"
        position={Position.Bottom}
        className="!bg-[var(--color-secondary)] !w-2 !h-2 !border-2 !border-[var(--color-surface)]"
      />
    </div>
  );
}

export const ToolNode = memo(ToolNodeComponent);