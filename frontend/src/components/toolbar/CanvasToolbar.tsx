import { useRef } from "react";
import { v4 as uuidv4 } from "uuid";
import { Plus, Trash2, Download, Upload } from "lucide-react";
import { useCanvasStore } from "@/store/canvasStore";
import { importCanvas } from "@/lib/api";
import type { CanvasSavePayload } from "@/types";

export function CanvasToolbar() {
  const canvasId = useCanvasStore((s) => s.canvasId);
  const canvasName = useCanvasStore((s) => s.canvasName);
  const setName = useCanvasStore((s) => s.setName);
  const nodes = useCanvasStore((s) => s.nodes);
  const setNodes = useCanvasStore((s) => s.setNodes);
  const edges = useCanvasStore((s) => s.edges);
  const setEdges = useCanvasStore((s) => s.setEdges);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const addAgent = () => {
    const newId = uuidv4();
    const newNode = {
      id: newId,
      type: "agent" as const,
      position: {
        x: 250 + Math.random() * 300,
        y: 150 + Math.random() * 300,
      },
      data: {
        id: newId,
        name: `Agent ${nodes.filter((n) => n.type === "agent").length + 1}`,
        role: "",
        instructions: "",
        modelName: "ollama:llama3.1",
        agentType: "worker",
      },
    };
    setNodes([...nodes, newNode]);
  };

  const addTool = () => {
    const newId = uuidv4();
    const newNode = {
      id: newId,
      type: "tool" as const,
      position: {
        x: 250 + Math.random() * 300,
        y: 150 + Math.random() * 300,
      },
      data: {
        id: newId,
        name: `Tool ${nodes.filter((n) => n.type === "tool").length + 1}`,
        code: "",
      },
    };
    setNodes([...nodes, newNode]);
  };

  const clearCanvas = () => {
    setNodes([]);
    setEdges([]);
  };

  const handleExport = () => {
    const payload: CanvasSavePayload = {
      name: canvasName,
      nodes: {
        agents: nodes
          .filter((n) => n.type === "agent")
          .map((n) => ({
            id: n.id,
            name: n.data.name as string,
            role: (n.data.role as string) || "",
            instructions: (n.data.instructions as string) || "",
            model_name: (n.data.modelName as string) || "ollama:llama3.1",
            agent_type: (n.data.agentType as string) || "worker",
            position_x: n.position.x,
            position_y: n.position.y,
          })),
        tools: nodes
          .filter((n) => n.type === "tool")
          .map((n) => ({
            id: n.id,
            name: n.data.name as string,
            code: (n.data.code as string) || "",
            position_x: n.position.x,
            position_y: n.position.y,
          })),
      },
      edges: edges.map((e) => ({
        id: e.id,
        source_node_id: e.source,
        target_node_id: e.target,
        edge_type: (e.data?.edgeType as string) || "tool_access",
      })),
    };

    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${canvasName.replace(/[^a-zA-Z0-9]/g, "_")}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleImport = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      const text = await file.text();
      const data = JSON.parse(text) as CanvasSavePayload;
      const imported = await importCanvas(data);

      const { setCanvas, setNodes, setEdges } = useCanvasStore.getState();
      setCanvas(imported.id, imported.name);

      const agentNodes = imported.nodes.agents.map((a) => ({
        id: a.id,
        type: "agent" as const,
        position: { x: a.position_x, y: a.position_y },
        data: {
          id: a.id,
          name: a.name,
          role: a.role,
          instructions: a.instructions,
          modelName: a.model_name,
          agentType: a.agent_type,
        },
      }));

      const toolNodes = imported.nodes.tools.map((t) => ({
        id: t.id,
        type: "tool" as const,
        position: { x: t.position_x, y: t.position_y },
        data: { id: t.id, name: t.name, code: t.code },
      }));

      setNodes([...agentNodes, ...toolNodes]);
      setEdges(
        imported.edges.map((e) => ({
          id: e.id,
          source: e.source_node_id,
          target: e.target_node_id,
          data: { edgeType: e.edge_type },
        }))
      );
    } catch (err) {
      console.error("Failed to import canvas:", err);
    }

    e.target.value = "";
  };

  return (
    <div className="h-12 bg-white border-b border-gray-200 flex items-center px-4 gap-3">
      <input
        type="text"
        value={canvasName}
        onChange={(e) => setName(e.target.value)}
        data-testid="canvas-name-input"
        className="text-sm font-semibold text-gray-800 bg-transparent border-b border-transparent hover:border-gray-300 focus:border-indigo-400 focus:outline-none px-1 py-0.5 w-48"
        placeholder="Canvas name"
      />

      <div className="w-px h-6 bg-gray-200" />

      <button
        onClick={addAgent}
        data-testid="add-agent-button"
        className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-md transition-colors"
      >
        <Plus className="w-3.5 h-3.5" />
        Agent
      </button>

      <button
        onClick={addTool}
        data-testid="add-tool-button"
        className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-white bg-amber-600 hover:bg-amber-700 rounded-md transition-colors"
      >
        <Plus className="w-3.5 h-3.5" />
        Tool
      </button>

      <button
        onClick={clearCanvas}
        data-testid="clear-canvas-button"
        className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-gray-600 hover:text-red-600 hover:bg-red-50 rounded-md transition-colors"
      >
        <Trash2 className="w-3.5 h-3.5" />
        Clear
      </button>

      <div className="w-px h-6 bg-gray-200" />

      <button
        onClick={handleExport}
        data-testid="export-button"
        className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-gray-600 hover:text-indigo-600 hover:bg-indigo-50 rounded-md transition-colors"
      >
        <Download className="w-3.5 h-3.5" />
        Export
      </button>

      <button
        onClick={handleImport}
        data-testid="import-button"
        className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-gray-600 hover:text-amber-600 hover:bg-amber-50 rounded-md transition-colors"
      >
        <Upload className="w-3.5 h-3.5" />
        Import
      </button>

      <input
        ref={fileInputRef}
        type="file"
        accept=".json"
        onChange={handleFileChange}
        className="hidden"
      />
    </div>
  );
}
