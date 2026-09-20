import { memo } from "react";
import { Handle, Position, NodeResizer, type NodeProps } from "@xyflow/react";
import { Wrench, Settings, Trash2 } from "lucide-react";
import type { ToolNodeData } from "@/types";
import { useCanvasStore } from "@/store/canvasStore";
import { HANDLE_IDS } from "@/lib/canvasConnectionRules";
import { deleteNodeWithConfirm } from "@/lib/nodeDeletion";

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
        relative h-full flex flex-col min-w-[180px] rounded-xl bg-[var(--color-surface)] border
        shadow-[0_4px_24px_-4px_rgba(0,0,0,0.5)]
        transition-all duration-200
        ${selected
          ? "border-[var(--color-info)] shadow-[0_0_0_1px_var(--color-info),0_4px_24px_-4px_var(--color-info-glow)]"
          : "border-[var(--color-border-default)]"
        }
        ${isActive ? "border-[var(--color-danger)] glow-active-pulse" : ""}
      `}
    >
      <NodeResizer
        isVisible={selected}
        minWidth={180}
        minHeight={90}
        handleClassName="!w-2 !h-2 !bg-[var(--color-surface)] !border-[var(--color-info)] !rounded-sm"
        lineClassName="!border-[var(--color-info)]/50"
      />
      <Handle
        id={HANDLE_IDS.toolTarget}
        type="target"
        position={Position.Top}
        className="!bg-[var(--color-text-tertiary)] !w-2 !h-2 !border-2 !border-[var(--color-surface)]"
      />
      <div className="flex items-center gap-2 px-3 py-2.5 bg-[var(--color-info-surface)] rounded-t-xl border-b border-[var(--color-info)]/10">
        <div className="flex items-center justify-center w-5 h-5 rounded-md bg-[var(--color-info-subtle)]">
          <Wrench className="w-3 h-3 text-[var(--color-info)]" />
        </div>
        <span className="font-semibold text-[13px] text-[var(--color-text-primary)] truncate flex-1">
          {toolData.name}
        </span>
        <span className="text-[12px] px-1.5 py-0.5 rounded-md font-semibold tracking-wide uppercase bg-[var(--color-info-subtle)] text-[var(--color-info)]">
          Tool
        </span>
        <button
          onPointerDown={(e) => e.nativeEvent.stopImmediatePropagation()}
          onClick={(e) => {
            e.stopPropagation();
            selectNode(id);
          }}
          className="p-1.5 text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] rounded-md hover:bg-[var(--color-elevated)] transition-all duration-150"
          title="Settings"
        >
          <Settings className="w-3.5 h-3.5" />
        </button>
        <button
          data-testid="tool-node-delete"
          onPointerDown={(e) => e.nativeEvent.stopImmediatePropagation()}
          onClick={(e) => {
            e.stopPropagation();
            void deleteNodeWithConfirm(id);
          }}
          className="p-1 text-[var(--color-text-tertiary)] hover:text-[var(--color-danger)] rounded-md hover:bg-[var(--color-elevated)] transition-all duration-150"
          title="Delete node"
          aria-label="Delete node"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
      <div className="px-3 py-2.5 flex-1 overflow-hidden">
        {codePreview ? (
          <pre className="text-[12px] text-[var(--color-text-tertiary)] font-[var(--font-mono)] leading-relaxed overflow-hidden">
            {codePreview}
          </pre>
        ) : (
          <p className="text-[13px] text-[var(--color-text-tertiary)] italic">Write Python code</p>
        )}
      </div>
      <Handle
        type="source"
        position={Position.Bottom}
        className="!bg-[var(--color-info)] !w-2 !h-2 !border-2 !border-[var(--color-surface)]"
      />
    </div>
  );
}

export const ToolNode = memo(ToolNodeComponent);