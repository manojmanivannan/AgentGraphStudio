import { useState } from "react";
import { v4 as uuidv4 } from "uuid";
import { Plus, Play, Square, Trash2 } from "lucide-react";
import { useCanvasStore } from "@/store/canvasStore";
import { useCanvasExecution } from "@/hooks/useCanvasExecution";

export function CanvasToolbar() {
  const [prompt, setPrompt] = useState("");
  const canvasId = useCanvasStore((s) => s.canvasId);
  const canvasName = useCanvasStore((s) => s.canvasName);
  const setName = useCanvasStore((s) => s.setName);
  const nodes = useCanvasStore((s) => s.nodes);
  const setNodes = useCanvasStore((s) => s.setNodes);
  const edges = useCanvasStore((s) => s.edges);
  const setEdges = useCanvasStore((s) => s.setEdges);
  const executionStatus = useCanvasStore((s) => s.executionStatus);
  const { run, abort } = useCanvasExecution();

  const addAgent = () => {
    const newId = uuidv4();
    const newNode = {
      id: newId,
      type: "agent" as const,
      position: { x: 250 + Math.random() * 300, y: 150 + Math.random() * 300 },
      data: { id: newId, name: `Agent ${nodes.filter((n) => n.type === "agent").length + 1}`, role: "", instructions: "", modelName: "ollama:llama3.1" },
    };
    setNodes([...nodes, newNode]);
  };

  const addTool = () => {
    const newId = uuidv4();
    const newNode = {
      id: newId,
      type: "tool" as const,
      position: { x: 250 + Math.random() * 300, y: 150 + Math.random() * 300 },
      data: { id: newId, name: `Tool ${nodes.filter((n) => n.type === "tool").length + 1}`, code: "" },
    };
    setNodes([...nodes, newNode]);
  };

  const clearCanvas = () => {
    setNodes([]);
    setEdges([]);
  };

  const handleRun = () => {
    if (!canvasId || !prompt.trim()) return;
    run(canvasId, prompt.trim());
  };

  const handleStop = () => {
    abort();
  };

  return (
    <div className="h-12 bg-white border-b border-gray-200 flex items-center px-4 gap-3">
      <input
        type="text"
        value={canvasName}
        onChange={(e) => setName(e.target.value)}
        className="text-sm font-semibold text-gray-800 bg-transparent border-b border-transparent hover:border-gray-300 focus:border-indigo-400 focus:outline-none px-1 py-0.5 w-48"
        placeholder="Canvas name"
      />

      <div className="w-px h-6 bg-gray-200" />

      <button
        onClick={addAgent}
        disabled={executionStatus === "running"}
        className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <Plus className="w-3.5 h-3.5" />
        Agent
      </button>

      <button
        onClick={addTool}
        disabled={executionStatus === "running"}
        className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-white bg-amber-600 hover:bg-amber-700 rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <Plus className="w-3.5 h-3.5" />
        Tool
      </button>

      <button
        onClick={clearCanvas}
        disabled={executionStatus === "running"}
        className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-gray-600 hover:text-red-600 hover:bg-red-50 rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <Trash2 className="w-3.5 h-3.5" />
        Clear
      </button>

      <div className="flex-1" />

      <div className="flex items-center gap-2">
        <input
          type="text"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") handleRun(); }}
          placeholder="Enter your prompt..."
          className="flex-1 px-2.5 py-1 text-xs border border-gray-200 rounded-md focus:outline-none focus:ring-1 focus:ring-indigo-400 focus:border-indigo-400 w-64"
          disabled={executionStatus === "running"}
        />

        {executionStatus === "running" ? (
          <button
            onClick={handleStop}
            className="flex items-center gap-1.5 px-3 py-1 text-xs font-medium text-white bg-red-600 hover:bg-red-700 rounded-md transition-colors"
          >
            <Square className="w-3 h-3" />
            Stop
          </button>
        ) : (
          <button
            onClick={handleRun}
            disabled={!prompt.trim() || !canvasId}
            className="flex items-center gap-1.5 px-3 py-1 text-xs font-medium text-white bg-green-600 hover:bg-green-700 rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Play className="w-3 h-3" />
            Run
          </button>
        )}
      </div>
    </div>
  );
}
