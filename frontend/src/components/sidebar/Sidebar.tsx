import { useState } from "react";
import { Settings, Play } from "lucide-react";
import { AgentEditor } from "./AgentEditor";
import { ToolEditor } from "./ToolEditor";
import { ExecutionLog } from "./ExecutionLog";
import { useCanvasStore } from "@/store/canvasStore";

type Tab = "properties" | "run";

export function Sidebar() {
  const [tab, setTab] = useState<Tab>("properties");
  const selectedNodeId = useCanvasStore((s) => s.selectedNodeId);
  const selectedNode = useCanvasStore.getState().nodes.find((n) => n.id === selectedNodeId);

  return (
    <div className="w-80 h-full border-l border-gray-200 bg-white flex flex-col">
      <div className="flex border-b border-gray-200">
        <button
          onClick={() => setTab("properties")}
          className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 text-xs font-medium transition-colors ${
            tab === "properties"
              ? "text-indigo-600 border-b-2 border-indigo-600 bg-indigo-50/50"
              : "text-gray-500 hover:text-gray-700"
          }`}
        >
          <Settings className="w-3.5 h-3.5" />
          Properties
        </button>
        <button
          onClick={() => setTab("run")}
          className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 text-xs font-medium transition-colors ${
            tab === "run"
              ? "text-indigo-600 border-b-2 border-indigo-600 bg-indigo-50/50"
              : "text-gray-500 hover:text-gray-700"
          }`}
        >
          <Play className="w-3.5 h-3.5" />
          Run
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {tab === "properties" && (
          <>
            {selectedNode?.type === "agent" && <AgentEditor />}
            {selectedNode?.type === "tool" && <ToolEditor />}
            {!selectedNode && (
              <div className="flex items-center justify-center h-full text-gray-400 text-sm">
                Select a node to edit its properties
              </div>
            )}
          </>
        )}
        {tab === "run" && <ExecutionLog />}
      </div>
    </div>
  );
}
