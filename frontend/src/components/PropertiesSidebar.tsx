import { Settings, X } from "lucide-react";
import { AgentEditor } from "@/components/sidebar/AgentEditor";
import { ToolEditor } from "@/components/sidebar/ToolEditor";
import { ResizablePanel } from "@/components/layout/ResizablePanel";
import { useCanvasStore } from "@/store/canvasStore";

export function PropertiesSidebar() {
  const selectedNodeId = useCanvasStore((s) => s.selectedNodeId);
  const selectNode = useCanvasStore((s) => s.selectNode);
  const propertiesOpen = useCanvasStore((s) => s.propertiesOpen);
  const toggleProperties = useCanvasStore((s) => s.toggleProperties);
  const nodes = useCanvasStore((s) => s.nodes);
  const selectedNode = nodes.find((n) => n.id === selectedNodeId);

  if (!propertiesOpen) {
    return (
      <div data-testid="properties-sidebar" className="w-12 h-full border-l border-[var(--color-border-subtle)] bg-[var(--color-surface)] flex flex-col items-center py-3 gap-3">
        <button
          onClick={toggleProperties}
          data-testid="properties-toggle"
          className="p-2 text-[var(--color-text-tertiary)] hover:text-[var(--color-accent)] hover:bg-[var(--color-accent-subtle)] rounded-lg transition-all duration-150"
          title="Open properties"
        >
          <Settings className="w-4 h-4" />
        </button>
        {selectedNodeId && (
          <div
            className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent)]"
            title="Node selected"
          />
        )}
      </div>
    );
  }

  return (
    <ResizablePanel
      data-testid="properties-sidebar"
      defaultWidth={256}
      minWidth={220}
      maxWidth={500}
      className="border-l border-[var(--color-border-subtle)] bg-[var(--color-surface)]"
    >
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-[var(--color-border-subtle)]">
        <span className="text-[11px] font-semibold text-[var(--color-text-tertiary)] uppercase tracking-[0.08em]">
          Properties
        </span>
        <button
          onClick={() => {
            selectNode(null);
          }}
          data-testid="properties-close"
          className="p-1 text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)] rounded-md hover:bg-[var(--color-elevated)] transition-all duration-150"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {selectedNode?.type === "agent" && <AgentEditor />}
        {selectedNode?.type === "tool" && <ToolEditor />}
        {!selectedNode && (
          <div className="flex items-center justify-center h-full text-[var(--color-text-tertiary)] text-[12px] text-center leading-relaxed">
            Select a node to edit its properties
          </div>
        )}
      </div>
    </ResizablePanel>
  );
}