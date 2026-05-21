import { useState } from "react";
import { Settings, X } from "lucide-react";
import { AgentEditor } from "@/components/sidebar/AgentEditor";
import { ToolEditor } from "@/components/sidebar/ToolEditor";
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
      <div data-testid="properties-sidebar" className="w-12 h-full border-l border-gray-200 bg-white flex flex-col items-center py-3 gap-3">
        <button
          onClick={toggleProperties}
          data-testid="properties-toggle"
          className="p-2 text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
          title="Open properties"
        >
          <Settings className="w-4 h-4" />
        </button>
        {selectedNodeId && (
          <div
            className="w-2 h-2 rounded-full bg-blue-500"
            title="Node selected"
          />
        )}
      </div>
    );
  }

  return (
    <div data-testid="properties-sidebar" className="w-64 h-full border-l border-gray-200 bg-white flex flex-col">
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200">
        <span className="text-xs font-semibold text-gray-600">
          Properties
        </span>
        <button
          onClick={() => {
            selectNode(null);
          }}
          data-testid="properties-close"
          className="p-1 text-gray-400 hover:text-gray-600 rounded"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {selectedNode?.type === "agent" && <AgentEditor />}
        {selectedNode?.type === "tool" && <ToolEditor />}
        {!selectedNode && (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm text-center">
            Select a node to edit its properties
          </div>
        )}
      </div>
    </div>
  );
}
