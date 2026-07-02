/**
 * @fileoverview Left sidebar for navigating between active conversations/sessions
 * within a specific canvas. Handles creation, deletion, import, and export of sessions.
 */

import { Link, useNavigate } from "react-router-dom";
import {
  Plus,
  MessageSquare,
  Home,
  Layout,
  Trash2,
  Download,
  Upload,
  Activity,
} from "lucide-react";
import type { ConversationSummary } from "@/types";

interface ChatSidebarProps {
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (val: boolean) => void;
  theme: "light" | "dark";
  canvasId: string | null;
  conversation_id?: string;
  conversations: ConversationSummary[];
  handleNewConversation: () => void;
  handleExportConversation: (e: React.MouseEvent, id: string, name: string) => void;
  setDeleteConfirmId: (id: string | null) => void;
  handleImportClick: () => void;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  handleFileChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
}

export function ChatSidebar({
  sidebarCollapsed,
  setSidebarCollapsed,
  theme,
  canvasId,
  conversation_id,
  conversations,
  handleNewConversation,
  handleExportConversation,
  setDeleteConfirmId,
  handleImportClick,
  fileInputRef,
  handleFileChange,
}: ChatSidebarProps) {
  const navigate = useNavigate();

  const navItemClass = (toPath: string) => {
    const isActive = location.pathname === toPath;
    if (sidebarCollapsed) {
      return `flex items-center justify-center w-10 h-10 mx-auto rounded-lg transition-all duration-150 ${
        isActive
          ? "bg-[var(--color-elevated)] border border-[var(--color-border-default)] shadow-sm"
          : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-overlay)]/40 border border-transparent"
      }`;
    }
    return `flex items-center gap-2.5 px-3 h-10 rounded-lg text-[13px] font-medium transition-all duration-150 ${
      isActive
        ? "bg-[var(--color-elevated)] border border-[var(--color-border-default)] text-[var(--color-text-primary)] shadow-sm"
        : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-overlay)]/40 border border-transparent"
    }`;
  };

  return (
    <aside className={`h-full border-r border-[var(--color-border-subtle)] bg-[var(--color-surface)] flex flex-col z-20 transition-[width] duration-300 ease-in-out overflow-hidden ${
      sidebarCollapsed ? "w-16" : "w-64"
    }`}>
      {/* Sidebar Header */}
      <div className="pt-4 pb-4 px-3 border-b border-[var(--color-border-subtle)] flex flex-col gap-2">
        {!sidebarCollapsed ? (
          <div className="flex items-center justify-between mb-2 w-full">
            <button
              onClick={() => setSidebarCollapsed(true)}
              data-testid="collapse-sidebar"
              className="flex items-center gap-2 cursor-pointer hover:opacity-80 active:scale-95 transition-all duration-200 w-full text-left"
              title="Collapse Sidebar"
            >
              <img
                src={theme === "dark" ? "/agent_graph_studio_logo_white.png" : "/agent_graph_studio_logo_dark.png"}
                alt="Logo"
                className="h-6 w-auto object-contain shrink-0"
              />
              <span className="font-bold text-[14px] tracking-tight text-[var(--color-text-primary)]">
                AgentGraph Studio
              </span>
            </button>
          </div>
        ) : (
          <div className="flex justify-center mb-2 w-full">
            <button
              onClick={() => setSidebarCollapsed(false)}
              data-testid="expand-sidebar"
              className="cursor-pointer hover:opacity-80 active:scale-95 transition-all duration-200"
              title="Expand Sidebar"
            >
              <img
                src={theme === "dark" ? "/agent_graph_studio_logo_white.png" : "/agent_graph_studio_logo_dark.png"}
                alt="Logo"
                className="h-6 w-auto object-contain"
              />
            </button>
          </div>
        )}

        <div className="space-y-1.5 w-full">
          <Link
            to="/"
            className={navItemClass("/")}
            title="Home"
          >
            <Home className="w-4 h-4 text-[var(--color-info)] shrink-0" />
            {!sidebarCollapsed && "Home"}
          </Link>
          {canvasId && (
            <Link
              to={`/canvas/${canvasId}`}
              className={navItemClass(`/canvas/${canvasId}`)}
              title="Canvas Editor"
            >
              <Layout className="w-4 h-4 text-[var(--color-accent)] shrink-0" />
              {!sidebarCollapsed && "Visual Canvas"}
            </Link>
          )}
          <button
            onClick={() => {
              if (canvasId) {
                navigate(`/chat/empty?canvas=${canvasId}`);
              } else {
                navigate(`/chat/empty`);
              }
            }}
            className={navItemClass("/chat")}
            title="Agent Chat"
          >
            <MessageSquare className="w-4 h-4 text-[var(--color-agent)] shrink-0" />
            {!sidebarCollapsed && "Agent Chat"}
          </button>
          <button
            onClick={() => window.open("/mlflow/", "_blank")}
            className={navItemClass("/mlflow")}
            title="Observability"
          >
            <Activity className="w-4 h-4 text-[var(--color-success)] shrink-0" />
            {!sidebarCollapsed && "Observability"}
          </button>
        </div>
      </div>

      {/* Sidebar Middle - Conversations List */}
      <div className="flex-1 overflow-y-auto p-3 space-y-1.5 w-full">
        {sidebarCollapsed ? (
          <div className="border-t border-[var(--color-border-subtle)] my-2" />
        ) : (
          <div className="px-2 py-1.5 text-[10px] font-semibold text-[var(--color-text-tertiary)] uppercase tracking-[0.08em] whitespace-nowrap">
            Recent Chats
          </div>
        )}
        {conversations.length === 0 && !sidebarCollapsed && (
          <div className="px-3 py-6 text-xs text-[var(--color-text-tertiary)] text-center font-light">
            No chats found for this canvas.
          </div>
        )}
        {conversations.map((c) => {
          const isActive = c.id === conversation_id;
          return (
            <div
              key={c.id}
              title={c.name}
              className={sidebarCollapsed
                ? `flex items-center justify-center w-10 h-10 mx-auto rounded-lg cursor-pointer transition-all duration-150 ${isActive
                    ? "bg-[var(--color-elevated)] border border-[var(--color-border-default)] text-[var(--color-text-primary)]"
                    : "hover:bg-[var(--color-overlay)]/40 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] border border-transparent"
                  }`
                : `group flex items-center justify-between px-3 h-10 rounded-lg cursor-pointer transition-all duration-150 ${isActive
                    ? "bg-[var(--color-elevated)] border border-[var(--color-border-default)] text-[var(--color-text-primary)]"
                    : "hover:bg-[var(--color-overlay)]/40 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] border border-transparent"
                  }`
              }
              onClick={() => navigate(`/chat/${c.id}`)}
            >
              {sidebarCollapsed ? (
                <MessageSquare className="w-3.5 h-3.5 text-[var(--color-text-tertiary)] shrink-0" />
              ) : (
                <>
                  <div className="flex items-center gap-2 truncate flex-1">
                    <MessageSquare className="w-3.5 h-3.5 text-[var(--color-text-tertiary)] shrink-0" />
                    <span className="text-xs truncate font-medium">{c.name}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={(e) => handleExportConversation(e, c.id, c.name)}
                      className="opacity-0 group-hover:opacity-100 p-1 text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-overlay)]/40 rounded transition-all duration-150"
                      title="Export conversation"
                    >
                      <Download className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setDeleteConfirmId(c.id);
                      }}
                      className="opacity-0 group-hover:opacity-100 p-1 text-[var(--color-text-tertiary)] hover:text-[var(--color-danger)] hover:bg-[var(--color-danger-subtle)] rounded transition-all duration-150"
                      title="Delete conversation"
                      data-testid={`delete-conv-${c.id}`}
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                </>
              )}
            </div>
          );
        })}
      </div>

      {/* Sidebar Bottom - Start New Conversation */}
      <div className={`p-3 border-t border-[var(--color-border-subtle)] bg-[var(--color-inset)] w-full flex flex-col ${sidebarCollapsed ? "items-center" : ""} gap-2`}>
        <button
          onClick={handleNewConversation}
          disabled={!canvasId}
          data-testid="new-chat-btn"
          className={sidebarCollapsed
            ? "btn-primary w-10 h-10 p-0 flex items-center justify-center rounded-lg"
            : "w-full btn-primary flex items-center justify-center gap-1.5 h-10 text-xs whitespace-nowrap"
          }
          title="New Conversation"
        >
          <Plus className="w-3.5 h-3.5 shrink-0" />
          {!sidebarCollapsed && <span className="truncate">New Conversation</span>}
        </button>
        <button
          onClick={handleImportClick}
          disabled={!canvasId}
          className={sidebarCollapsed
            ? "btn-secondary w-10 h-10 p-0 flex items-center justify-center rounded-lg border border-[var(--color-border-default)]"
            : "w-full btn-secondary flex items-center justify-center gap-1.5 h-10 text-xs whitespace-nowrap border border-[var(--color-border-default)]"
          }
          title="Import Conversation"
        >
          <Upload className="w-3.5 h-3.5 shrink-0" />
          {!sidebarCollapsed && <span className="truncate">Import Conversation</span>}
        </button>
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileChange}
          accept=".zip"
          className="hidden"
        />
      </div>
    </aside>
  );
}
