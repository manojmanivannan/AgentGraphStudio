import { useRef, useState } from "react";
import { v4 as uuidv4 } from "uuid";
import {
  Brain,
  Wrench,
  Trash2,
  Download,
  Upload,
  Sun,
  Moon,
  GitBranch,
} from "lucide-react";
import { useCanvasStore } from "@/store/canvasStore";
import { useThemeStore } from "@/store/themeStore";
import { importCanvas } from "@/lib/api";
import type { CanvasSavePayload } from "@/types";
import { RailItem } from "./RailItem";
import { RailPopover } from "./RailPopover";

export function SidebarRail() {
  const canvasId = useCanvasStore((s) => s.canvasId);
  const canvasName = useCanvasStore((s) => s.canvasName);
  const nodes = useCanvasStore((s) => s.nodes);
  const setNodes = useCanvasStore((s) => s.setNodes);
  const setEdges = useCanvasStore((s) => s.setEdges);
  const setCanvas = useCanvasStore((s) => s.setCanvas);
  const theme = useThemeStore((s) => s.theme);
  const toggleTheme = useThemeStore((s) => s.toggleTheme);

  const addAgentRef = useRef<HTMLButtonElement>(null);
  const clearRef = useRef<HTMLButtonElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [addAgentOpen, setAddAgentOpen] = useState(false);
  const [clearOpen, setClearOpen] = useState(false);

  /** Calculate a position in the center of the current canvas viewport,
   *  with slight randomness so multiple nodes don't stack. */
  const getViewportCenterPosition = () => {
    const { x, y, zoom } = useCanvasStore.getState().viewport;
    const railWidth = 48;
    // Center of the visible canvas area in screen pixels
    const screenCenterX = railWidth + (window.innerWidth - railWidth) / 2;
    const screenCenterY = window.innerHeight / 2;
    // Convert screen center to flow coordinates
    const flowX = (screenCenterX - x) / zoom;
    const flowY = (screenCenterY - y) / zoom;
    // Add randomness within ±80px (in flow coords) so nodes don't overlap
    return {
      x: flowX + (Math.random() - 0.5) * 160,
      y: flowY + (Math.random() - 0.5) * 160,
    };
  };

  const addAgent = (agentType: "worker" | "router") => {
    const newId = uuidv4();
    const newNode = {
      id: newId,
      type: "agent" as const,
      position: getViewportCenterPosition(),
      style: { width: 280 },
      data: {
        id: newId,
        name: `Agent ${nodes.filter((n) => n.type === "agent").length + 1}`,
        role: "",
        instructions: "",
        modelName: "ollama:llama3.1",
        agentType,
      },
    };
    setNodes([...nodes, newNode]);
    setAddAgentOpen(false);
  };

  const addTool = () => {
    const newId = uuidv4();
    const newNode = {
      id: newId,
      type: "tool" as const,
      position: getViewportCenterPosition(),
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
    setClearOpen(false);
  };

  const handleExport = () => {
    const edges = useCanvasStore.getState().edges;
    const payload: CanvasSavePayload = {
      name: canvasName,
      nodes: {
        agents: nodes
          .filter((n) => n.type === "agent")
          .map((n) => ({
            id: n.id,
            name: (n.data as any).name as string,
            role: ((n.data as any).role as string) || "",
            instructions: ((n.data as any).instructions as string) || "",
            model_name: ((n.data as any).modelName as string) || "ollama:llama3.1",
            agent_type: ((n.data as any).agentType as string) || "worker",
            enable_memory: ((n.data as any).enableMemory as boolean) ?? false,
            enable_conversation_history:
              ((n.data as any).enableConversationHistory as boolean) ?? false,
            enable_rag: ((n.data as any).enableRag as boolean) ?? false,
            rag_chunk_size: ((n.data as any).ragChunkSize as number) ?? 1000,
            position_x: n.position.x,
            position_y: n.position.y,
          })),
        tools: nodes
          .filter((n) => n.type === "tool")
          .map((n) => ({
            id: n.id,
            name: (n.data as any).name as string,
            code: ((n.data as any).code as string) || "",
            packages: ((n.data as any).packages as string) || "",
            args: ((n.data as any).args as []) || [],
            position_x: n.position.x,
            position_y: n.position.y,
          })),
      },
      edges: edges.map((e) => ({
        id: e.id,
        source_node_id: e.source,
        target_node_id: e.target,
        edge_type: ((e.data as any)?.edgeType as string) || "tool_access",
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
          enableRag: a.enable_rag,
          ragChunkSize: a.rag_chunk_size,
        },
      }));

      const toolNodes = imported.nodes.tools.map((t) => ({
        id: t.id,
        type: "tool" as const,
        position: { x: t.position_x, y: t.position_y },
        style: { width: 220 },
        data: { id: t.id, name: t.name, code: t.code, packages: t.packages },
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

  const isDark = theme === "dark";

  return (
    <div
      data-testid="sidebar-rail"
      className="absolute left-0 top-0 bottom-0 w-12 chrome-glass border-r border-[var(--color-border-subtle)] flex flex-col items-center py-3 gap-1 z-40"
    >
      {/* Create section */}
      <div className="relative">
        <RailItem
          ref={addAgentRef}
          icon={Brain}
          label="Add Agent"
          onClick={() => setAddAgentOpen((prev) => !prev)}
          data-testid="add-agent-button"
        />
        <RailPopover
          open={addAgentOpen}
          onClose={() => setAddAgentOpen(false)}
          anchorRef={addAgentRef}
        >
          <button
            onClick={() => addAgent("worker")}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-[13px] text-[var(--color-text-secondary)] hover:text-[var(--color-accent)] hover:bg-[var(--color-accent-subtle)] rounded-md transition-colors"
          >
            <Brain className="w-3.5 h-3.5 text-[var(--color-accent)]" />
            Worker
          </button>
          <button
            onClick={() => addAgent("router")}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-[13px] text-[var(--color-text-secondary)] hover:text-[var(--color-agent)] hover:bg-[var(--color-agent-subtle)] rounded-md transition-colors"
          >
            <GitBranch className="w-3.5 h-3.5 text-[var(--color-agent)]" />
            Router
          </button>
        </RailPopover>
      </div>

      <RailItem
        icon={Wrench}
        label="Add Tool"
        onClick={addTool}
        data-testid="add-tool-button"
      />

      {/* Divider */}
      <div className="w-6 h-px bg-[var(--color-border-subtle)] my-2" />

      {/* Canvas actions */}
      <div className="relative">
        <RailItem
          ref={clearRef}
          icon={Trash2}
          label="Clear Canvas"
          onClick={() => setClearOpen((prev) => !prev)}
          danger
          data-testid="clear-canvas-button"
        />
        <RailPopover
          open={clearOpen}
          onClose={() => setClearOpen(false)}
          anchorRef={clearRef}
        >
          <div className="px-3 py-2">
            <p className="text-[12px] text-[var(--color-text-secondary)] mb-2">
              Clear all nodes and edges?
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setClearOpen(false)}
                className="btn-ghost text-[11px] px-2 py-1"
              >
                Cancel
              </button>
              <button
                onClick={clearCanvas}
                className="btn-danger-ghost text-[11px] px-2 py-1"
              >
                Clear
              </button>
            </div>
          </div>
        </RailPopover>
      </div>

      <RailItem
        icon={Download}
        label="Export"
        onClick={handleExport}
        data-testid="export-button"
      />

      <RailItem
        icon={Upload}
        label="Import"
        onClick={handleImport}
        data-testid="import-button"
      />

      {/* Spacer */}
      <div className="flex-1" />

      {/* Divider */}
      <div className="w-6 h-px bg-[var(--color-border-subtle)] my-2" />

      {/* Theme toggle */}
      <RailItem
        icon={isDark ? Moon : Sun}
        label={isDark ? "Light Mode" : "Dark Mode"}
        onClick={toggleTheme}
        data-testid="theme-toggle"
      />

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