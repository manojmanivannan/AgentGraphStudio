import { useRef } from "react";
import { v4 as uuidv4 } from "uuid";
import { Plus, Trash2, Download, Upload, Brain, Wrench } from "lucide-react";
import { useCanvasStore } from "@/store/canvasStore";
import { importCanvas } from "@/lib/api";
import type { CanvasSavePayload } from "@/types";
import { ThemeToggle } from "@/components/ThemeToggle";

export function CanvasToolbar() {
  const canvasId = useCanvasStore((s) => s.canvasId);
  const canvasName = useCanvasStore((s) => s.canvasName);
  const setName = useCanvasStore((s) => s.setName);
  const nodes = useCanvasStore((s) => s.nodes);
  const setNodes = useCanvasStore((s) => s.setNodes);
  const setEdges = useCanvasStore((s) => s.setEdges);
  const edges = useCanvasStore((s) => s.edges);
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
      style: { width: 280 },
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
      style: { width: 220 },
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
            enable_memory: (n.data.enableMemory as boolean) ?? false,
            enable_conversation_history: (n.data.enableConversationHistory as boolean) ?? false,
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
        style: { width: 280 },
        data: {
          id: a.id,
          name: a.name,
          role: a.role,
          instructions: a.instructions,
          modelName: a.model_name,
          agentType: a.agent_type,
          enableMemory: a.enable_memory,
          enableConversationHistory: a.enable_conversation_history,
        },
      }));

      const toolNodes = imported.nodes.tools.map((t) => ({
        id: t.id,
        type: "tool" as const,
        position: { x: t.position_x, y: t.position_y },
        style: { width: 220 },
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
    <div className="h-12 bg-[var(--color-surface)] border-b border-[var(--color-border-subtle)] flex items-center px-4 gap-2">
      {/* Canvas Name */}
      <input
        type="text"
        value={canvasName}
        onChange={(e) => setName(e.target.value)}
        data-testid="canvas-name-input"
        className="text-sm font-semibold text-[var(--color-text-primary)] bg-transparent border-b border-transparent hover:border-[var(--color-border-default)] focus:border-[var(--color-accent)] focus:outline-none px-1 py-0.5 w-48 placeholder:text-[var(--color-text-tertiary)] transition-colors"
        placeholder="Canvas name"
      />

      <div className="w-px h-5 bg-[var(--color-border-subtle)] mx-1" />

      {/* Add Agent */}
      <button
        onClick={addAgent}
        data-testid="add-agent-button"
        className="btn-primary text-[11px] py-1.5 px-2.5"
      >
        <Brain className="w-3.5 h-3.5" />
        Agent
      </button>

      {/* Add Tool */}
      <button
        onClick={addTool}
        data-testid="add-tool-button"
        className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] font-semibold text-[var(--color-text-inverse)] rounded-lg transition-all duration-200"
        style={{
          background: "linear-gradient(135deg, var(--color-secondary) 0%, var(--color-secondary-dim) 100%)",
        }}
      >
        <Wrench className="w-3.5 h-3.5" />
        Tool
      </button>

      {/* Clear */}
      <button
        onClick={clearCanvas}
        data-testid="clear-canvas-button"
        className="btn-danger-ghost"
      >
        <Trash2 className="w-3.5 h-3.5" />
        Clear
      </button>

      <div className="w-px h-5 bg-[var(--color-border-subtle)] mx-1" />

      {/* Export */}
      <button
        onClick={handleExport}
        data-testid="export-button"
        className="btn-ghost"
      >
        <Download className="w-3.5 h-3.5" />
        Export
      </button>

      {/* Import */}
      <button
        onClick={handleImport}
        data-testid="import-button"
        className="btn-ghost"
      >
        <Upload className="w-3.5 h-3.5" />
        Import
      </button>

      <div className="flex-1" />

      {/* Theme Toggle */}
      <ThemeToggle />

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