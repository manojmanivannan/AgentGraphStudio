import { useEffect, useState, useRef } from "react";
import { Routes, Route, useNavigate, useParams, Link, useLocation, Navigate } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import ChatPage from "@/components/chat/ChatPage";
import ObservabilityPage from "@/components/observability/ObservabilityPage";
import LoginPage from "@/components/auth/LoginPage";
import RegisterPage from "@/components/auth/RegisterPage";
import AccountPage from "@/components/account/AccountPage";
import { RequireAuth, RedirectIfAuthed } from "@/components/auth/guards";
import { useAuthStore } from "@/store/authStore";
import { onUnauthorized } from "@/lib/api";
import { useCanvasStore } from "@/store/canvasStore";
import {
  createCanvas,
  listCanvases,
  getCanvas,
  deleteCanvas,
  importCanvas,
  importCanvasZip,
  logout as logoutApi,
} from "@/lib/api";
import { decodeCanvasResponse } from "@/lib/canvasGraphCodec";
import {
  Plus,
  FileText,
  Workflow,
  Upload,
  Trash2,
  Search,
  AlertCircle,
  X,
  HelpCircle,
  Check,
  MessageSquare,
  UserCog,
  LogOut,
} from "lucide-react";
import type { CanvasListItem, CanvasSavePayload } from "@/types";
import type { Node } from "@xyflow/react";
import { ThemeToggle } from "@/components/ThemeToggle";
import { useThemeStore } from "@/store/themeStore";

function getRelativeTimeString(dateStr: string): string {
  try {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return "just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays === 1) return "yesterday";
    return `${diffDays}d ago`;
  } catch {
    return "";
  }
}

// Canvas Editor Wrapper
function CanvasEditorPage({
  loading,
  setLoading,
  error,
  setError,
}: {
  loading: boolean;
  setLoading: (l: boolean) => void;
  error: string | null;
  setError: (e: string | null) => void;
}) {
  const { canvas_id } = useParams<{ canvas_id: string }>();
  const canvasId = useCanvasStore((s) => s.canvasId);
  const setCanvas = useCanvasStore((s) => s.setCanvas);
  const setNodes = useCanvasStore((s) => s.setNodes);
  const setEdges = useCanvasStore((s) => s.setEdges);
  const navigate = useNavigate();

  const handleOpenCanvas = async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      const canvas = await getCanvas(id);
      setCanvas(canvas.id, canvas.name);

      const decoded = decodeCanvasResponse(canvas);
      setNodes(decoded.nodes);
      setEdges(decoded.edges);
    } catch (err: any) {
      setError(err?.message || "Failed to open canvas.");
      console.error("Failed to open canvas:", err);
      navigate("/");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (canvas_id) {
      handleOpenCanvas(canvas_id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canvas_id]);

  if (loading && !canvasId) {
    return (
      <div className="min-h-screen w-full bg-[var(--color-base)] flex items-center justify-center">
        <div className="flex gap-1.5">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent)] animate-pulse"
              style={{ animationDelay: `${i * 0.15}s` }}
            />
          ))}
        </div>
      </div>
    );
  }

  return <AppShell />;
}

// Landing Page Wrapper
function LandingPage({
  canvases,
  loadCanvases,
  loading,
  setLoading,
  error,
  setError,
  searchQuery,
  setSearchQuery,
  deleteConfirmIds,
  setDeleteConfirmIds,
  selectMode,
  setSelectMode,
  selectedCanvasIds,
  toggleSelectCanvas,
  handleToggleSelectAll,
  handleCancelSelect,
  dragActive,
  setDragActive,
  fileInputRef,
  handleCreateCanvas,
  handleImportFile,
  handleDeleteCanvases,
}: {
  canvases: CanvasListItem[];
  loadCanvases: () => Promise<void>;
  loading: boolean;
  setLoading: (l: boolean) => void;
  error: string | null;
  setError: (e: string | null) => void;
  searchQuery: string;
  setSearchQuery: (q: string) => void;
  deleteConfirmIds: string[] | null;
  setDeleteConfirmIds: (ids: string[] | null) => void;
  selectMode: boolean;
  setSelectMode: (mode: boolean) => void;
  selectedCanvasIds: Set<string>;
  toggleSelectCanvas: (id: string) => void;
  handleToggleSelectAll: (filteredCanvases: CanvasListItem[]) => void;
  handleCancelSelect: () => void;
  dragActive: boolean;
  setDragActive: (active: boolean) => void;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  handleCreateCanvas: () => Promise<void>;
  handleImportFile: (file: File) => Promise<void>;
  handleDeleteCanvases: (ids: string[]) => Promise<void>;
}) {
  const navigate = useNavigate();
  const resetStore = useCanvasStore((s) => s.reset);
  const theme = useThemeStore((s) => s.theme);
  const user = useAuthStore((s) => s.user);
  const clearAuth = useAuthStore((s) => s.clear);
  const [loggingOut, setLoggingOut] = useState(false);

  useEffect(() => {
    resetStore();
    loadCanvases();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleLogout = async () => {
    setLoggingOut(true);
    try {
      await logoutApi();
    } catch (err) {
      // Even if the backend call fails (network down, server error), clear the
      // local session and return to /login — the cookie is httpOnly so we
      // can't clear it client-side, but the user is effectively logged out of
      // this client. They'll be re-prompted on next /auth/me.
      console.error("Logout request failed:", err);
    } finally {
      clearAuth();
      setLoggingOut(false);
      navigate("/login", { replace: true });
    }
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      const isZip =
        file.name.toLowerCase().endsWith(".zip") ||
        file.type === "application/zip" ||
        file.type === "application/x-zip-compressed";
      const isJson =
        file.name.toLowerCase().endsWith(".json") ||
        file.type === "application/json";

      if (isZip || isJson) {
        await handleImportFile(file);
      } else {
        setError("Only ZIP archives (.zip) and JSON files (.json) are supported.");
      }
    }
  };

  const filteredCanvases = canvases.filter((c) =>
    c.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div
      className="h-screen w-full bg-gradient-to-b from-[var(--color-base)] to-[var(--color-inset)] flex flex-col items-center py-16 px-4 md:px-8 noise-bg relative overflow-y-auto"
      onDragEnter={handleDrag}
      onDragOver={handleDrag}
      onDragLeave={handleDrag}
      onDrop={handleDrop}
    >
      {/* Hidden File Input */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".zip,.json"
        data-testid="file-input"
        onChange={async (e) => {
          if (e.target.files && e.target.files[0]) {
            await handleImportFile(e.target.files[0]);
          }
        }}
        className="hidden"
      />

      {/* Ambient background glow */}
      <div className="absolute top-1/4 left-1/3 w-[500px] h-[500px] bg-[var(--color-accent)] opacity-[0.03] rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/3 w-[400px] h-[400px] bg-[var(--color-secondary)] opacity-[0.02] rounded-full blur-[100px] pointer-events-none" />
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-gradient-to-tr from-slate-500 to-zinc-400 opacity-[0.03] rounded-full blur-[130px] pointer-events-none" />

      {/* Header */}
      <header className="w-full max-w-4xl flex items-center justify-between mb-12 relative z-10">
        <div className="flex items-center gap-3">
          <img
            src={theme === "dark" ? "/agent_graph_studio_logo_white.png" : "/agent_graph_studio_logo_dark.png"}
            alt="Logo"
            className="h-8 w-auto object-contain"
          />
          <div>
            <h1 className="text-xl font-bold tracking-tight text-[var(--color-text-primary)]">
              AgentGraph Studio
            </h1>
            <p className="text-xs text-[var(--color-text-tertiary)] font-light">
              Visual Multi-Agent Workflow Orchestrator
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <ThemeToggle className="!border !border-[var(--color-border-default)] hover:bg-[var(--color-elevated)] shadow-[0_2px_8px_rgba(0,0,0,0.2)]" />
          {user && (
            <Link
              to="/account"
              title="Account"
              className="flex items-center justify-center w-9 h-9 rounded-lg border border-[var(--color-border-default)] text-[var(--color-text-secondary)] hover:bg-[var(--color-elevated)] hover:text-[var(--color-text-primary)] transition-colors"
            >
              <UserCog className="w-4 h-4" />
            </Link>
          )}
          {user && (
            <button
              onClick={handleLogout}
              disabled={loggingOut}
              data-testid="logout-button"
              title="Log out"
              className="flex items-center justify-center w-9 h-9 rounded-lg border border-[var(--color-border-default)] text-[var(--color-text-secondary)] hover:bg-[var(--color-elevated)] hover:text-[var(--color-danger)] transition-colors disabled:opacity-50 cursor-pointer"
            >
              <LogOut className="w-4 h-4" />
            </button>
          )}
        </div>
      </header>

      {/* Error Alert */}
      {error && (
        <div className="w-full max-w-4xl p-4 mb-6 rounded-xl bg-[var(--color-danger-subtle)] border border-[var(--color-danger)]/30 text-[var(--color-danger)] flex items-start gap-3 relative z-10 animate-fade-in shadow-[0_4px_12px_rgba(0,0,0,0.2)]">
          <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-xs font-semibold">Operation Failed</p>
            <p className="text-xs opacity-90">{error}</p>
          </div>
          <button
            onClick={() => setError(null)}
            className="text-[var(--color-danger)] hover:opacity-75"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Hero Cards Grid */}
      <div className={`grid grid-cols-1 ${canvases.length > 0 ? "md:grid-cols-3" : "md:grid-cols-2"} gap-6 w-full max-w-4xl mb-12 relative z-10`}>
        {/* New Canvas Card */}
        <button
          onClick={handleCreateCanvas}
          disabled={loading}
          className="group relative flex flex-col items-start p-6 rounded-2xl bg-gradient-to-br from-[var(--color-surface)] to-[var(--color-elevated)] border border-[var(--color-border-default)] hover:border-[var(--color-accent)] transition-all duration-300 text-left shadow-[0_4px_20px_rgba(0,0,0,0.35),0_0_12px_rgba(255,255,255,0.02)] hover:shadow-[0_0_30px_-5px_rgba(20,184,166,0.15),0_0_15px_rgba(255,255,255,0.04),0_8px_32px_-4px_rgba(0,0,0,0.5)] disabled:opacity-40"
        >
          <div className="w-12 h-12 rounded-xl bg-[var(--color-accent-subtle)] border border-[var(--color-border-default)] flex items-center justify-center text-[var(--color-accent)] group-hover:scale-110 transition-transform duration-300 mb-4 shadow-inner">
            <Plus className="w-6 h-6" />
          </div>
          <h3 className="text-lg font-semibold text-[var(--color-text-primary)] mb-1">
            New Canvas
          </h3>
          <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">
            Start building a custom multi-agent system from scratch using the interactive visual node designer.
          </p>
          <div className="absolute bottom-4 right-4 text-xs text-[var(--color-accent)] font-semibold opacity-0 group-hover:opacity-100 transition-opacity duration-300">
            Create &rarr;
          </div>
        </button>

        {/* Import ZIP Card */}
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={loading}
          className="group relative flex flex-col items-start p-6 rounded-2xl bg-gradient-to-br from-[var(--color-surface)] to-[var(--color-elevated)] border border-[var(--color-border-default)] hover:border-[var(--color-secondary)] transition-all duration-300 text-left shadow-[0_4px_20px_rgba(0,0,0,0.35),0_0_12px_rgba(255,255,255,0.02)] hover:shadow-[0_0_30px_-5px_rgba(245,158,11,0.15),0_0_15px_rgba(255,255,255,0.04),0_8px_32px_-4px_rgba(0,0,0,0.5)] disabled:opacity-40"
        >
          <div className="w-12 h-12 rounded-xl bg-[var(--color-secondary-subtle)] border border-[var(--color-border-default)] flex items-center justify-center text-[var(--color-secondary)] group-hover:scale-110 transition-transform duration-300 mb-4 shadow-inner">
            <Upload className="w-6 h-6" />
          </div>
          <h3 className="text-lg font-semibold text-[var(--color-text-primary)] mb-1">
            Import Canvas
          </h3>
          <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">
            Upload a `.zip` archive or `.json` file containing agent configurations, custom tool code, and RAG document artifacts.
          </p>
          <div className="absolute bottom-4 right-4 text-xs text-[var(--color-secondary)] font-semibold opacity-0 group-hover:opacity-100 transition-opacity duration-300">
            Upload &rarr;
          </div>
        </button>

        {/* Agent Chat Card */}
        {canvases.length > 0 && (
          <button
            onClick={() => {
              const canvasId = canvases[0]?.id;
              if (canvasId) {
                navigate(`/chat/empty?canvas=${canvasId}`);
              } else {
                navigate(`/chat/empty`);
              }
            }}
            disabled={loading}
            className="group relative flex flex-col items-start p-6 rounded-2xl bg-gradient-to-br from-[var(--color-surface)] to-[var(--color-elevated)] border border-[var(--color-border-default)] hover:border-[var(--color-agent)] transition-all duration-300 text-left shadow-[0_4px_20px_rgba(0,0,0,0.35),0_0_12px_rgba(255,255,255,0.02)] hover:shadow-[0_0_30px_-5px_rgba(99,102,241,0.15),0_0_15px_rgba(255,255,255,0.04),0_8px_32px_-4px_rgba(0,0,0,0.5)] disabled:opacity-40"
          >
            <div className="w-12 h-12 rounded-xl bg-[var(--color-agent-subtle)] border border-[var(--color-border-default)] flex items-center justify-center text-[var(--color-agent)] group-hover:scale-110 transition-transform duration-300 mb-4 shadow-inner">
              <MessageSquare className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-semibold text-[var(--color-text-primary)] mb-1">
              Agent Chat
            </h3>
            <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">
              Start chatting with your agent workflow, ask questions, run tool actions, and orchestrate agent task completion.
            </p>
            <div className="absolute bottom-4 right-4 text-xs text-[var(--color-agent)] font-semibold opacity-0 group-hover:opacity-100 transition-opacity duration-300">
              Chat &rarr;
            </div>
          </button>
        )}
      </div>

      {/* Loading Spinner */}
      {loading && (
        <div className="flex justify-center mb-8 relative z-10">
          <div className="flex gap-1.5">
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent)]"
                style={{
                  animation: "dotPulse 1.2s ease-in-out infinite",
                  animationDelay: `${i * 0.15}s`,
                }}
              />
            ))}
          </div>
        </div>
      )}

      {/* Recent Canvases Section */}
      <div
        className="w-full max-w-4xl relative z-10 animate-fade-in"
      >
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4 px-1">
          <div className="flex items-center gap-3">
            <h2 className="text-[11px] font-semibold text-[var(--color-text-tertiary)] uppercase tracking-[0.1em]">
              Recent Canvases
            </h2>
            {canvases.length > 0 && !selectMode && (
              <button
                onClick={() => setSelectMode(true)}
                className="btn-secondary text-[10px] px-2 py-0.5 rounded-md font-medium cursor-pointer"
              >
                Select
              </button>
            )}
            {selectMode && (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleToggleSelectAll(filteredCanvases)}
                  className="btn-secondary text-[10px] px-2 py-0.5 rounded-md font-medium cursor-pointer"
                >
                  {filteredCanvases.length > 0 && filteredCanvases.every((c) => selectedCanvasIds.has(c.id))
                    ? "Deselect All"
                    : "Select All"}
                </button>
                <button
                  onClick={handleCancelSelect}
                  className="btn-secondary text-[10px] px-2 py-0.5 rounded-md font-medium cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  onClick={() => setDeleteConfirmIds(Array.from(selectedCanvasIds))}
                  disabled={selectedCanvasIds.size === 0}
                  className="btn-primary bg-[var(--color-danger)] hover:bg-red-600 text-white text-[10px] px-2 py-0.5 rounded-md font-medium disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed"
                >
                  Delete Selected ({selectedCanvasIds.size})
                </button>
              </div>
            )}
          </div>
          {canvases.length > 0 && (
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--color-text-tertiary)]" />
              <input
                type="text"
                placeholder="Search canvases..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full sm:w-64 pl-9 pr-4 py-1.5 bg-[var(--color-surface)] border border-[var(--color-border-default)] rounded-lg text-xs outline-none focus:border-[var(--color-accent)] transition-colors text-[var(--color-text-primary)] placeholder-[var(--color-text-tertiary)]"
              />
            </div>
          )}
        </div>

        {canvases.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-12 rounded-2xl bg-gradient-to-br from-[var(--color-surface)] to-[var(--color-elevated)] border border-[var(--color-border-subtle)] text-center shadow-[0_4px_20px_rgba(0,0,0,0.3)]">
            <HelpCircle className="w-8 h-8 text-[var(--color-text-tertiary)] mb-3 animate-pulse" />
            <p className="text-sm text-[var(--color-text-secondary)]">
              No canvases created yet. Build a new workflow or import one from ZIP to get started!
            </p>
          </div>
        ) : filteredCanvases.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-12 rounded-2xl bg-gradient-to-br from-[var(--color-surface)] to-[var(--color-elevated)] border border-[var(--color-border-subtle)] text-center shadow-[0_4px_20px_rgba(0,0,0,0.3)]">
            <HelpCircle className="w-8 h-8 text-[var(--color-text-tertiary)] mb-3" />
            <p className="text-sm text-[var(--color-text-secondary)]">
              No canvases match your search.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {filteredCanvases.map((c, i) => (
              <div
                key={c.id}
                style={{ animation: `staggerFadeIn 0.4s ease-out ${0.05 * i}s both` }}
                onClick={() => {
                  if (selectMode) {
                    toggleSelectCanvas(c.id);
                  }
                }}
                className={`group relative flex items-center justify-between p-4 bg-gradient-to-r from-[var(--color-surface)] to-[var(--color-elevated)] border rounded-xl transition-all duration-300 shadow-[0_4px_16px_rgba(0,0,0,0.25)] hover:shadow-[0_0_24px_-4px_rgba(116,116,139,0.18),0_0_8px_-2px_rgba(116,116,139,0.08),0_4px_12px_rgba(0,0,0,0.35)] ${selectMode
                  ? selectedCanvasIds.has(c.id)
                    ? "border-[var(--color-accent)]"
                    : "border-[var(--color-border-subtle)] hover:border-[var(--color-border-default)] cursor-pointer"
                  : "border-[var(--color-border-subtle)] hover:border-[var(--color-border-default)]"
                  }`}
              >
                {selectMode && (
                  <div
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleSelectCanvas(c.id);
                    }}
                    className={`w-4.5 h-4.5 rounded border flex items-center justify-center shrink-0 cursor-pointer transition-all mr-2 ${selectedCanvasIds.has(c.id)
                      ? "border-[var(--color-accent)] bg-[var(--color-accent)] text-black"
                      : "border-[var(--color-border-strong)] bg-[var(--color-inset)] hover:border-[var(--color-text-secondary)]"
                      }`}
                  >
                    {selectedCanvasIds.has(c.id) && <Check className="w-3 h-3 stroke-[3]" />}
                  </div>
                )}
                <Link
                  to={selectMode ? "#" : `/canvas/${c.id}`}
                  onClick={(e) => {
                    if (selectMode) {
                      e.preventDefault();
                    }
                  }}
                  className="flex-1 flex items-center gap-3 text-left overflow-hidden"
                >
                  <div className="w-9 h-9 rounded-lg bg-[var(--color-inset)] border border-[var(--color-border-subtle)] flex items-center justify-center text-[var(--color-text-secondary)] group-hover:text-[var(--color-accent)] group-hover:border-[var(--color-accent-subtle)] transition-all">
                    <FileText className="w-4 h-4" />
                  </div>
                  <div className="truncate pr-4">
                    <span className="block text-[13px] font-semibold text-[var(--color-text-primary)] truncate">
                      {c.name}
                    </span>
                    <span className="block text-[11px] text-[var(--color-text-tertiary)] font-light mt-0.5">
                      {c.updated_at
                        ? `Updated ${getRelativeTimeString(c.updated_at)}`
                        : c.created_at
                          ? `Created ${getRelativeTimeString(c.created_at)}`
                          : "Recent"}
                    </span>
                  </div>
                </Link>
                {!selectMode && (
                  <button
                    onClick={() => setDeleteConfirmIds([c.id])}
                    disabled={loading}
                    className="opacity-0 group-hover:opacity-100 p-2 text-[var(--color-text-tertiary)] hover:text-[var(--color-danger)] hover:bg-[var(--color-danger-subtle)] rounded-lg transition-all cursor-pointer"
                    title="Delete canvas"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Drag and Drop Overlay */}
      {dragActive && (
        <div
          className="fixed inset-0 bg-[var(--color-base)]/80 backdrop-blur-md z-50 flex flex-col items-center justify-center border-4 border-dashed border-[var(--color-accent)] m-4 rounded-3xl animate-fade-in"
          onDragEnter={handleDrag}
          onDragOver={handleDrag}
          onDragLeave={handleDrag}
          onDrop={handleDrop}
        >
          <div className="w-20 h-20 rounded-2xl bg-[var(--color-accent-subtle)] border border-[var(--color-accent)]/50 flex items-center justify-center text-[var(--color-accent)] mb-4 animate-bounce">
            <Upload className="w-10 h-10" />
          </div>
          <h2 className="text-2xl font-bold text-[var(--color-text-primary)] mb-2">
            Drop ZIP or JSON to Import
          </h2>
          <p className="text-sm text-[var(--color-text-secondary)]">
            Release to upload and load your agent graph canvas.
          </p>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deleteConfirmIds && deleteConfirmIds.length > 0 && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div
            className="w-full max-w-sm p-6 rounded-2xl bg-[var(--color-surface)] border border-[var(--color-border-strong)] shadow-2xl animate-fade-in"
          >
            <h3 className="text-base font-semibold delete-modal-title mb-2">
              {deleteConfirmIds.length === 1 ? "Delete Canvas?" : `Delete ${deleteConfirmIds.length} Canvases?`}
            </h3>
            <p className="text-xs text-[var(--color-text-secondary)] mb-6 leading-relaxed">
              {deleteConfirmIds.length === 1 ? (
                <>
                  Are you sure you want to delete{" "}
                  <strong className="text-[var(--color-text-primary)]">
                    "{canvases.find((c) => c.id === deleteConfirmIds[0])?.name}"
                  </strong>
                  ?
                </>
              ) : (
                <>
                  Are you sure you want to delete the{" "}
                  <strong className="text-[var(--color-text-primary)]">
                    {deleteConfirmIds.length}
                  </strong>{" "}
                  selected canvases?
                </>
              )}{" "}
              This will permanently remove all agents, tools, configurations,
              and RAG documents associated with {deleteConfirmIds.length === 1 ? "this canvas" : "these canvases"}.
              This action cannot be undone.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setDeleteConfirmIds(null)}
                className="btn-secondary text-xs px-4 py-2 cursor-pointer"
                disabled={loading}
              >
                Cancel
              </button>
              <button
                onClick={() => handleDeleteCanvases(deleteConfirmIds)}
                className="btn-primary bg-[var(--color-danger)] hover:bg-red-600 text-white text-xs px-4 py-2 cursor-pointer"
                disabled={loading}
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function AppRoutes() {
  const navigate = useNavigate();
  const location = useLocation();

  const [canvases, setCanvases] = useState<CanvasListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const [deleteConfirmIds, setDeleteConfirmIds] = useState<string[] | null>(null);
  const [selectMode, setSelectMode] = useState(false);
  const [selectedCanvasIds, setSelectedCanvasIds] = useState<Set<string>>(new Set());

  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadCanvases = async () => {
    try {
      const list = await listCanvases();
      setCanvases(list);
    } catch {
      setCanvases([]);
    }
  };

  // Support deep-linking via ?canvas=<id> (redirects to the clean route)
  useEffect(() => {
    if (location.pathname !== "/") return;
    const params = new URLSearchParams(location.search);
    const initialId = params.get("canvas");
    if (initialId) {
      navigate(`/canvas/${initialId}`, { replace: true });
    }
  }, [navigate, location.pathname, location.search]);

  const handleCreateCanvas = async () => {
    setLoading(true);
    setError(null);
    try {
      const canvas = await createCanvas();
      navigate(`/canvas/${canvas.id}`);
    } catch (err: any) {
      setError(err?.message || "Failed to create canvas.");
      console.error("Failed to create canvas:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleImportFile = async (file: File) => {
    setLoading(true);
    setError(null);
    try {
      const isZip = file.name.toLowerCase().endsWith(".zip");
      const canvas = isZip
        ? await importCanvasZip(file)
        : await importCanvas(JSON.parse(await file.text()) as CanvasSavePayload);
      navigate(`/canvas/${canvas.id}`);
    } catch (err: any) {
      setError(err?.message || "Failed to import canvas package.");
      console.error("Import failure:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteCanvases = async (ids: string[]) => {
    setLoading(true);
    setError(null);
    try {
      await Promise.all(ids.map((id) => deleteCanvas(id)));
      setDeleteConfirmIds(null);
      setSelectedCanvasIds(new Set());
      setSelectMode(false);
      await loadCanvases();
    } catch (err: any) {
      setError(err?.message || "Failed to delete canvas.");
      console.error("Canvas deletion failure:", err);
    } finally {
      setLoading(false);
    }
  };

  const toggleSelectCanvas = (id: string) => {
    setSelectedCanvasIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleToggleSelectAll = (filteredCanvases: CanvasListItem[]) => {
    const allSelected = filteredCanvases.length > 0 && filteredCanvases.every((c) => selectedCanvasIds.has(c.id));
    if (allSelected) {
      setSelectedCanvasIds((prev) => {
        const next = new Set(prev);
        filteredCanvases.forEach((c) => next.delete(c.id));
        return next;
      });
    } else {
      setSelectedCanvasIds((prev) => {
        const next = new Set(prev);
        filteredCanvases.forEach((c) => next.add(c.id));
        return next;
      });
    }
  };

  const handleCancelSelect = () => {
    setSelectMode(false);
    setSelectedCanvasIds(new Set());
  };

  return (
    <Routes>
      {/* Auth routes — bounce authed users to the app */}
      <Route element={<RedirectIfAuthed />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
      </Route>

      {/* Protected app routes — bounce unauthed users to /login */}
      <Route element={<RequireAuth />}>
        <Route
          path="/"
          element={
            <LandingPage
              canvases={canvases}
              loadCanvases={loadCanvases}
              loading={loading}
              setLoading={setLoading}
              error={error}
              setError={setError}
              searchQuery={searchQuery}
              setSearchQuery={setSearchQuery}
              deleteConfirmIds={deleteConfirmIds}
              setDeleteConfirmIds={setDeleteConfirmIds}
              selectMode={selectMode}
              setSelectMode={setSelectMode}
              selectedCanvasIds={selectedCanvasIds}
              toggleSelectCanvas={toggleSelectCanvas}
              handleToggleSelectAll={handleToggleSelectAll}
              handleCancelSelect={handleCancelSelect}
              dragActive={dragActive}
              setDragActive={setDragActive}
              fileInputRef={fileInputRef}
              handleCreateCanvas={handleCreateCanvas}
              handleImportFile={handleImportFile}
              handleDeleteCanvases={handleDeleteCanvases}
            />
          }
        />
        <Route
          path="/canvas/:canvas_id"
          element={
            <CanvasEditorPage
              loading={loading}
              setLoading={setLoading}
              error={error}
              setError={setError}
            />
          }
        />
        <Route path="/chat/:conversation_id" element={<ChatPage />} />
        <Route path="/observability/:canvas_id" element={<ObservabilityPage />} />
        <Route path="/account" element={<AccountPage />} />
      </Route>

      {/* Unknown routes → home (the guard there redirects to /login if needed) */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function BootSplash() {
  return (
    <div className="min-h-screen w-full bg-[var(--color-base)] flex items-center justify-center">
      <div className="flex gap-1.5">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent)] animate-pulse"
            style={{ animationDelay: `${i * 0.15}s` }}
          />
        ))}
      </div>
    </div>
  );
}

export default function App() {
  const status = useAuthStore((s) => s.status);
  const hydrate = useAuthStore((s) => s.hydrate);
  const navigate = useNavigate();

  // Hydrate the session from the server-side cookie once on boot so a refresh
  // keeps the user logged in.
  useEffect(() => {
    if (useAuthStore.getState().status === "unknown") {
      hydrate();
    }
  }, [hydrate]);

  // Surface stale-session (401) from any protected data call: clear the auth
  // state and send the user to /login.
  useEffect(() => {
    return onUnauthorized(() => {
      useAuthStore.getState().clear();
      navigate("/login", { replace: true });
    });
  }, [navigate]);

  if (status === "unknown") {
    return <BootSplash />;
  }

  return <AppRoutes />;
}