import { X, Brain, Wrench, GitBranch } from "lucide-react";
import { useCanvasStore } from "@/store/canvasStore";
import { OverlayPanel } from "@/components/layout/OverlayPanel";
import { AgentEditor } from "@/components/sidebar/AgentEditor";
import { ToolEditor } from "@/components/sidebar/ToolEditor";

export function PropertiesOverlay() {
  const selectedNodeId = useCanvasStore((s) => s.selectedNodeId);
  const selectNode = useCanvasStore((s) => s.selectNode);
  const nodes = useCanvasStore((s) => s.nodes);
  const propertiesWidth = useCanvasStore((s) => s.propertiesWidth);
  const setPropertiesWidth = useCanvasStore((s) => s.setPropertiesWidth);

  const selectedNode = nodes.find((n) => n.id === selectedNodeId);
  const isOpen = selectedNodeId !== null;

  // Since chat overlay is removed, properties overlay always sits at the right edge
  const offsetRight = 0;

  const handleClose = () => {
    selectNode(null);
  };

  return (
    <OverlayPanel
      open={isOpen}
      width={propertiesWidth}
      offsetRight={offsetRight}
      onClose={handleClose}
      resizable={true}
      onWidthChange={setPropertiesWidth}
      minWidth={240}
      maxWidth={600}
      data-testid="properties-overlay"
    >
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-[var(--color-border-subtle)]">
        <div className="flex items-center gap-2">
          {selectedNode?.type === "agent" && (
            <>
              {(selectedNode.data as any)?.agentType === "router" ? (
                <GitBranch className="w-4 h-4 text-[var(--color-agent)]" />
              ) : (
                <Brain className="w-4 h-4 text-[var(--color-accent)]" />
              )}
            </>
          )}
          {selectedNode?.type === "tool" && (
            <Wrench className="w-4 h-4 text-[var(--color-secondary)]" />
          )}
          <span className="text-[13px] font-semibold text-[var(--color-text-primary)] truncate">
            {selectedNode
              ? (selectedNode.data as any)?.name ?? "Properties"
              : "Properties"}
          </span>
        </div>
        <button
          onClick={handleClose}
          data-testid="properties-close"
          className="p-1 text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)] rounded-md hover:bg-[var(--color-elevated)] transition-all duration-150"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {selectedNode?.type === "agent" && <AgentEditor />}
        {selectedNode?.type === "tool" && <ToolEditor />}
      </div>
    </OverlayPanel>
  );
}