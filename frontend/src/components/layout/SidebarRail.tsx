import { useRef, useState } from "react";
import { v4 as uuidv4 } from "uuid";
import { Link, useNavigate } from "react-router-dom";
import {
  Brain,
  Wrench,
  Trash2,
  Download,
  Upload,
  GitBranch,
  FolderKanban,
  Layout,
  MessageSquare,
  Home,
  Activity,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { useCanvasStore } from "@/store/canvasStore";
import { useThemeStore } from "@/store/themeStore";
import {
  exportCanvasZip,
  importCanvas,
  importCanvasZip,
  listConversations,
  createConversation,
} from "@/lib/api";
import type { CanvasSavePayload } from "@/types";
import { RailPopover } from "./RailPopover";

export function SidebarRail() {
  const canvasId = useCanvasStore((s) => s.canvasId);
  const theme = useThemeStore((s) => s.theme);
  const canvasName = useCanvasStore((s) => s.canvasName);
  const nodes = useCanvasStore((s) => s.nodes);
  const setNodes = useCanvasStore((s) => s.setNodes);
  const setEdges = useCanvasStore((s) => s.setEdges);
  const setCanvas = useCanvasStore((s) => s.setCanvas);
  const sidebarCollapsed = useCanvasStore((s) => s.sidebarCollapsed);
  const setSidebarCollapsed = useCanvasStore((s) => s.setSidebarCollapsed);

  const navigate = useNavigate();

  const clearRef = useRef<HTMLButtonElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [clearOpen, setClearOpen] = useState(false);

  /** Calculate a position in the center of the current canvas viewport,
   *  with slight randomness so multiple nodes don't stack. */
  const getViewportCenterPosition = () => {
    const { x, y, zoom } = useCanvasStore.getState().viewport;
    const railWidth = sidebarCollapsed ? 64 : 256;
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

  const handleExport = async () => {
    if (canvasId) {
      try {
        const blob = await exportCanvasZip(canvasId);
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${canvasName.replace(/[^a-zA-Z0-9]/g, "_")}.zip`;
        a.click();
        URL.revokeObjectURL(url);
        return;
      } catch (err) {
        console.error("ZIP export failed, falling back to JSON export:", err);
      }
    }

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
      const imported = file.name.toLowerCase().endsWith(".zip")
        ? await importCanvasZip(file)
        : await importCanvas(JSON.parse(await file.text()) as CanvasSavePayload);

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

  const handleChatClick = async () => {
    if (!canvasId) return;
    try {
      const convs = await listConversations(canvasId);
      if (convs && convs.length > 0) {
        navigate(`/chat/${convs[0].id}`);
      } else {
        const newConv = await createConversation(canvasId, "New Conversation");
        navigate(`/chat/${newConv.id}`);
      }
    } catch (err) {
      console.error("Failed to list/create conversations in SidebarRail:", err);
      try {
        const newConv = await createConversation(canvasId, "New Conversation");
        navigate(`/chat/${newConv.id}`);
      } catch (e) {
        console.error("Fallback new conversation creation failed:", e);
      }
    }
  };

  const navItemClass = (toPath: string, testId?: string) => {
    const isExact = window.location.pathname === toPath;
    const isChat = toPath === "/chat" && window.location.pathname.startsWith("/chat/");
    const isActive = isExact || isChat;
    
    return sidebarCollapsed
      ? `flex items-center justify-center w-10 h-10 mx-auto rounded-lg transition-all ${
          isActive
            ? "bg-[var(--color-elevated)] text-[var(--color-text-primary)] border border-[var(--color-border-default)]"
            : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-elevated)]"
        }`
      : `flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
          isActive
            ? "bg-[var(--color-elevated)] text-[var(--color-text-primary)] border border-[var(--color-border-default)]"
            : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-elevated)]"
        }`;
  };

  const workerBtnClass = sidebarCollapsed
    ? "flex items-center justify-center w-10 h-10 mx-auto rounded-lg text-[var(--color-text-secondary)] hover:text-[var(--color-accent)] hover:bg-[var(--color-accent-subtle)] transition-all cursor-pointer"
    : "w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-accent)] hover:bg-[var(--color-accent-subtle)] transition-colors text-left cursor-pointer";

  const routerBtnClass = sidebarCollapsed
    ? "flex items-center justify-center w-10 h-10 mx-auto rounded-lg text-[var(--color-text-secondary)] hover:text-[var(--color-agent)] hover:bg-[var(--color-agent-subtle)] transition-all cursor-pointer"
    : "w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-agent)] hover:bg-[var(--color-agent-subtle)] transition-colors text-left cursor-pointer";

  const toolBtnClass = sidebarCollapsed
    ? "flex items-center justify-center w-10 h-10 mx-auto rounded-lg text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-elevated)] transition-all cursor-pointer"
    : "w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-elevated)] transition-colors text-left cursor-pointer";

  const importExportBtnClass = sidebarCollapsed
    ? "flex items-center justify-center w-10 h-10 mx-auto rounded-lg text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-elevated)] transition-all cursor-pointer"
    : "w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-elevated)] transition-colors text-left cursor-pointer";

  const clearBtnClass = sidebarCollapsed
    ? "flex items-center justify-center w-10 h-10 mx-auto rounded-lg text-[var(--color-text-secondary)] hover:text-[var(--color-danger)] hover:bg-[var(--color-danger-subtle)] transition-all cursor-pointer"
    : "w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-danger)] hover:bg-[var(--color-danger-subtle)] transition-colors text-left cursor-pointer";

  return (
    <aside
      data-testid="sidebar-rail"
      className={`absolute left-0 top-0 bottom-0 ${
        sidebarCollapsed ? "w-16" : "w-64"
      } border-r border-[var(--color-border-subtle)] bg-[var(--color-surface)] flex flex-col z-40 transition-[width] duration-300 ease-in-out overflow-hidden`}
    >
      {/* Sidebar Header */}
      <div className={`p-4 border-b border-[var(--color-border-subtle)] flex flex-col gap-2 ${sidebarCollapsed ? "items-center" : ""}`}>
        {!sidebarCollapsed ? (
          <div className="flex items-center justify-between mb-2 w-full">
            <div className="flex items-center gap-2">
              <img
                src={theme === "dark" ? "/agent_graph_studio_logo_white.png" : "/agent_graph_studio_logo_dark.png"}
                alt="Logo"
                className="h-6 w-auto object-contain shrink-0"
              />
              <span className="font-bold text-[14px] tracking-tight text-[var(--color-text-primary)]">
                AgentGraph Studio
              </span>
            </div>
            <button
              onClick={() => setSidebarCollapsed(true)}
              data-testid="collapse-sidebar"
              className="p-1 rounded hover:bg-[var(--color-elevated)] text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] transition-colors cursor-pointer"
              title="Collapse Sidebar"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3 mb-2 w-full">
            <img
              src={theme === "dark" ? "/agent_graph_studio_logo_white.png" : "/agent_graph_studio_logo_dark.png"}
              alt="Logo"
              className="h-6 w-auto object-contain"
            />
            <button
              onClick={() => setSidebarCollapsed(false)}
              data-testid="expand-sidebar"
              className="p-1.5 rounded hover:bg-[var(--color-elevated)] text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] transition-colors cursor-pointer"
              title="Expand Sidebar"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        )}

        <div className="space-y-1 w-full">
          <Link
            to="/"
            className={navItemClass("/")}
            title="Home"
          >
            <Home className="w-4 h-4 text-[var(--color-text-tertiary)] shrink-0" />
            {!sidebarCollapsed && "Home"}
          </Link>
          {canvasId && (
            <Link
              to={`/canvas/${canvasId}`}
              className={navItemClass(`/canvas/${canvasId}`)}
              title="Canvas Editor"
            >
              <Layout className="w-4 h-4 text-[var(--color-text-tertiary)] shrink-0" />
              {!sidebarCollapsed && "Visual Canvas"}
            </Link>
          )}
          <button
            onClick={handleChatClick}
            data-testid="chat-toggle"
            className={navItemClass("/chat", "chat-toggle")}
            title="Agent Chat"
          >
            <MessageSquare className="w-4 h-4 text-[var(--color-text-tertiary)] shrink-0" />
            {!sidebarCollapsed && "Agent Chat"}
          </button>
          <button
            onClick={() => window.open("/mlflow/", "_blank")}
            data-testid="observability-toggle"
            className={navItemClass("/mlflow")}
            title="Observability"
          >
            <Activity className="w-4 h-4 text-[var(--color-text-tertiary)] shrink-0" />
            {!sidebarCollapsed && "Observability"}
          </button>
        </div>
      </div>

      {/* Sidebar Content (Middle actions) */}
      <div className="flex-1 p-4 space-y-4 overflow-y-auto w-full">
        {/* Build Section */}
        <div>
          {sidebarCollapsed ? (
            <div className="border-t border-[var(--color-border-subtle)] my-2" />
          ) : (
            <h3 className="text-[10px] font-semibold text-[var(--color-text-tertiary)] uppercase tracking-wider mb-2">
              Build
            </h3>
          )}
          <div className="space-y-1.5">
            <button
              onClick={() => addAgent("worker")}
              data-testid="add-agent-worker"
              className={workerBtnClass}
              title="Add Worker Agent"
            >
              <Brain className="w-4 h-4 text-[var(--color-accent)] shrink-0" />
              {!sidebarCollapsed && "Add Worker Agent"}
            </button>
            <button
              onClick={() => addAgent("router")}
              data-testid="add-agent-router"
              className={routerBtnClass}
              title="Add Router Agent"
            >
              <GitBranch className="w-4 h-4 text-[var(--color-agent)] shrink-0" />
              {!sidebarCollapsed && "Add Router Agent"}
            </button>
            <button
              onClick={addTool}
              data-testid="add-tool-button"
              className={toolBtnClass}
              title="Add Custom Tool"
            >
              <Wrench className="w-4 h-4 text-[var(--color-text-tertiary)] shrink-0" />
              {!sidebarCollapsed && "Add Custom Tool"}
            </button>
          </div>
        </div>

        {/* Manage Section */}
        <div>
          {sidebarCollapsed ? (
            <div className="border-t border-[var(--color-border-subtle)] my-2" />
          ) : (
            <h3 className="text-[10px] font-semibold text-[var(--color-text-tertiary)] uppercase tracking-wider mb-2">
              Manage Canvas
            </h3>
          )}
          <div className="space-y-1.5">
            <button
              onClick={handleImport}
              data-testid="import-button"
              className={importExportBtnClass}
              title="Import Agent Canvas"
            >
              <Upload className="w-4 h-4 text-[var(--color-text-tertiary)] shrink-0" />
              {!sidebarCollapsed && "Import Agent Canvas"}
            </button>
            <button
              onClick={handleExport}
              data-testid="export-button"
              className={importExportBtnClass}
              title="Export Agent Canvas"
            >
              <Download className="w-4 h-4 text-[var(--color-text-tertiary)] shrink-0" />
              {!sidebarCollapsed && "Export Agent Canvas"}
            </button>

            {/* Clear Canvas */}
            <div className="relative">
              <button
                ref={clearRef}
                onClick={() => setClearOpen((prev) => !prev)}
                data-testid="clear-canvas-button"
                className={clearBtnClass}
                title="Clear Canvas"
              >
                <Trash2 className="w-4 h-4 text-[var(--color-text-tertiary)] shrink-0" />
                {!sidebarCollapsed && "Clear Canvas"}
              </button>

              <RailPopover
                open={clearOpen}
                onClose={() => setClearOpen(false)}
                anchorRef={clearRef}
              >
                <div className="p-3">
                  <p className="text-[11px] text-[var(--color-text-secondary)] mb-2 whitespace-nowrap">
                    Clear all nodes and edges?
                  </p>
                  <div className="flex gap-2 justify-end">
                    <button
                      onClick={() => setClearOpen(false)}
                      className="btn-ghost text-[10px] px-2 py-1"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={clearCanvas}
                      className="btn-danger-ghost text-[10px] px-2 py-1"
                    >
                      Clear
                    </button>
                  </div>
                </div>
              </RailPopover>
            </div>
          </div>
        </div>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept=".json,.zip"
        onChange={handleFileChange}
        className="hidden"
      />
    </aside>
  );
}