import { memo } from "react";
import { Handle, Position, NodeResizer, type NodeProps } from "@xyflow/react";
import { Paperclip, Settings, Trash2 } from "lucide-react";
import type { AttachmentNodeData } from "@/types";
import { useCanvasStore } from "@/store/canvasStore";
import { HANDLE_IDS } from "@/lib/canvasConnectionRules";
import { deleteNodeWithConfirm } from "@/lib/nodeDeletion";

function AttachmentNodeComponent({ id, data, selected }: NodeProps) {
  const attachmentData = data as unknown as AttachmentNodeData;
  const activeNodeId = useCanvasStore((s) => s.activeNodeId);
  const selectNode = useCanvasStore((s) => s.selectNode);
  const isActive = activeNodeId === attachmentData.id;

  return (
    <div
      data-testid="attachment-node"
      data-node-id={id}
      className={`
        relative h-full flex flex-col min-w-[160px] rounded-xl bg-[var(--color-surface)] border
        shadow-[0_4px_24px_-4px_rgba(0,0,0,0.5)]
        transition-all duration-200
        ${selected
          ? "border-[var(--color-warning)] shadow-[0_0_0_1px_var(--color-warning),0_4px_24px_-4px_var(--color-warning-glow)]"
          : "border-[var(--color-border-default)]"
        }
        ${isActive ? "border-[var(--color-danger)] glow-active-pulse" : ""}
      `}
    >
      <NodeResizer
        isVisible={selected}
        minWidth={160}
        minHeight={80}
        handleClassName="!w-2 !h-2 !bg-[var(--color-surface)] !border-[var(--color-warning)] !rounded-sm"
        lineClassName="!border-[var(--color-warning)]/50"
      />
      <Handle
        id={HANDLE_IDS.attachmentProducesTarget}
        type="target"
        position={Position.Top}
        className="!bg-[var(--color-text-tertiary)] !w-2 !h-2 !border-2 !border-[var(--color-surface)]"
      />
      <div className="flex items-center gap-2 px-2.5 py-2 bg-[var(--color-warning-surface)] rounded-t-xl border-b border-[var(--color-warning)]/10">
        <div className="flex items-center justify-center w-4 h-4 rounded-md bg-[var(--color-warning-subtle)]">
          <Paperclip className="w-2.5 h-2.5 text-[var(--color-warning)]" />
        </div>
        <span className="font-semibold text-[12px] text-[var(--color-text-primary)] truncate flex-1">
          {attachmentData.name}
        </span>
        <span className="text-[9px] px-1.5 py-0.5 rounded-md font-semibold tracking-wide uppercase bg-[var(--color-warning-subtle)] text-[var(--color-warning)]">
          {attachmentData.fileType?.toUpperCase()}
        </span>
        <button
          onPointerDown={(e) => e.nativeEvent.stopImmediatePropagation()}
          onClick={(e) => {
            e.stopPropagation();
            selectNode(id);
          }}
          className="p-0.5 text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] rounded-md hover:bg-[var(--color-elevated)] transition-all duration-150"
          title="Settings"
        >
          <Settings className="w-3 h-3" />
        </button>
        <button
          data-testid="attachment-node-delete"
          onPointerDown={(e) => e.nativeEvent.stopImmediatePropagation()}
          onClick={(e) => {
            e.stopPropagation();
            void deleteNodeWithConfirm(id);
          }}
          className="p-0.5 text-[var(--color-text-tertiary)] hover:text-[var(--color-danger)] rounded-md hover:bg-[var(--color-elevated)] transition-all duration-150"
          title="Delete node"
          aria-label="Delete node"
        >
          <Trash2 className="w-3 h-3" />
        </button>
      </div>
      <div className="px-2.5 py-2 flex-1 overflow-hidden">
        {attachmentData.description ? (
          <p className="text-[13px] text-[var(--color-text-secondary)] line-clamp-2 leading-relaxed">
            {attachmentData.description}
          </p>
        ) : (
          <p className="text-[13px] text-[var(--color-text-tertiary)] italic">
            No description
          </p>
        )}
      </div>
      <Handle
        id={HANDLE_IDS.attachmentConsumesSource}
        type="source"
        position={Position.Bottom}
        className="!bg-[var(--color-warning)] !w-2 !h-2 !border-2 !border-[var(--color-surface)]"
      />
    </div>
  );
}

export const AttachmentNode = memo(AttachmentNodeComponent);
