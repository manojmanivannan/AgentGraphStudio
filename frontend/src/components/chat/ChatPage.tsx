/**
 * @fileoverview Main Chat Page layout orchestrator. Combines the ChatSidebar,
 * MessageTurn sequence, and input area. Defers WebSocket state management to
 * useChatWebSocket.
 */

import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { useParams, useNavigate, useSearchParams, useLocation } from "react-router-dom";
import {
  Send,
  Plus,
  MessageSquare,
  Square,
  AlertCircle,
} from "lucide-react";
import { useCanvasStore } from "@/store/canvasStore";
import { useThemeStore } from "@/store/themeStore";
import { AccountControls } from "@/components/layout/AccountControls";
import {
  createConversation,
  listConversations,
  getConversationById,
  deleteConversationById,
  getCanvas,
  apiOrigin,
  exportConversationZip,
  importConversationZip,
  listCanvases,
} from "@/lib/api";
import type { ConversationSummary, Message, CanvasResponse, CanvasListItem } from "@/types";
import { MessageTurn } from "./MessageTurn";
import { ChatSidebar } from "./ChatSidebar";
import { useChatWebSocket } from "./useChatWebSocket";

interface TurnGroup {
  id: string;
  userMessage: Message;
  steps: Message[];
  humanInterrupt?: Message;
  finalAnswer?: Message;
  isStreaming: boolean;
}

function renderMessageContent(content: string, isToolResult: boolean = false) {
  if (!content) return null;

  // Render markdown images like ![alt](url)
  const regex = /!\[(.*?)\]\((.*?)\)/g;
  const parts = [];
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(content)) !== null) {
    const textBefore = content.substring(lastIndex, match.index);
    if (textBefore) {
      parts.push({ type: 'text', value: textBefore });
    }
    const alt = match[1];
    let url = match[2];
    
    // Resolve relative backend URLs using apiOrigin
    if (url.startsWith('/')) {
      url = `${apiOrigin}${url}`;
    }
    
    parts.push({ type: 'image', value: url, alt });
    lastIndex = regex.lastIndex;
  }

  const textAfter = content.substring(lastIndex);
  if (textAfter) {
    parts.push({ type: 'text', value: textAfter });
  }

  if (parts.length === 0) {
    return <div className="whitespace-pre-wrap">{content}</div>;
  }

  return (
    <div className="flex flex-col gap-2">
      {parts.map((part, idx) => {
        if (part.type === 'image') {
          return (
            <img
              key={idx}
              src={part.value}
              alt={part.alt || "Image"}
              className="max-w-full rounded border border-[var(--color-border-subtle)] shadow-sm my-1"
            />
          );
        } else {
          return (
            <div key={idx} className="whitespace-pre-wrap">
              {part.value}
            </div>
          );
        }
      })}
    </div>
  );
}

export function groupMessagesIntoTurns(messages: Message[]): {
  preTurnMessages: Message[];
  turns: TurnGroup[];
} {
  const preTurnMessages: Message[] = [];
  const turns: TurnGroup[] = [];
  let currentTurn: TurnGroup | null = null;

  for (const msg of messages) {
    if (msg.role === "user") {
      currentTurn = {
        id: msg.id,
        userMessage: msg,
        steps: [],
        finalAnswer: undefined,
        isStreaming: true,
      };
      turns.push(currentTurn);
    } else if (currentTurn) {
      if (msg.event_type === "final_answer") {
        currentTurn.finalAnswer = msg;
        currentTurn.isStreaming = false;
      } else if (msg.event_type === "human_input_request" || msg.event_type === "tool_approval_request") {
        currentTurn.humanInterrupt = msg;
        currentTurn.isStreaming = false;
        currentTurn.steps.push(msg);
      } else {
        currentTurn.steps.push(msg);
        currentTurn.finalAnswer = undefined;
        currentTurn.isStreaming = true;
      }
    } else {
      preTurnMessages.push(msg);
    }
  }

  return { preTurnMessages, turns };
}

function computeNestingLevels(canvasData: CanvasResponse): Record<string, number> {
  const levels: Record<string, number> = {};
  const agents = canvasData.nodes?.agents || [];
  const tools = canvasData.nodes?.tools || [];
  const edges = canvasData.edges || [];

  const adj: Record<string, string[]> = {};
  const hasIncoming = new Set<string>();

  for (const edge of edges) {
    if (!adj[edge.source_node_id]) {
      adj[edge.source_node_id] = [];
    }
    adj[edge.source_node_id].push(edge.target_node_id);
    hasIncoming.add(edge.target_node_id);
  }

  const roots = agents.filter(a => !hasIncoming.has(a.id));
  const initialNodes = roots.length > 0 ? roots : agents;

  const queue: { id: string; level: number }[] = [];
  const visited = new Set<string>();

  for (const node of initialNodes) {
    levels[node.id] = 0;
    queue.push({ id: node.id, level: 0 });
    visited.add(node.id);
  }

  while (queue.length > 0) {
    const { id, level } = queue.shift()!;
    const targets = adj[id] || [];
    for (const targetId of targets) {
      if (!visited.has(targetId)) {
        visited.add(targetId);
        levels[targetId] = level + 1;
        queue.push({ id: targetId, level: level + 1 });
      }
    }
  }

  for (const agent of agents) {
    if (!visited.has(agent.id)) {
      levels[agent.id] = 0;
      queue.push({ id: agent.id, level: 0 });
      visited.add(agent.id);

      while (queue.length > 0) {
        const { id, level } = queue.shift()!;
        const targets = adj[id] || [];
        for (const targetId of targets) {
          if (!visited.has(targetId)) {
            visited.add(targetId);
            levels[targetId] = level + 1;
            queue.push({ id: targetId, level: level + 1 });
          }
        }
      }
    }
  }

  return levels;
}

export default function ChatPage() {
  const { conversation_id } = useParams<{ conversation_id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();

  const theme = useThemeStore((s) => s.theme);
  const sidebarCollapsed = useCanvasStore((s) => s.sidebarCollapsed);
  const setSidebarCollapsed = useCanvasStore((s) => s.setSidebarCollapsed);

  const [canvasId, setCanvasId] = useState<string | null>(null);
  const [canvasName, setCanvasName] = useState<string>("Canvas");
  const [canvas, setCanvas] = useState<CanvasResponse | null>(null);
  const [conversationName, setConversationName] = useState<string>("Chat");
  const [allCanvases, setAllCanvases] = useState<CanvasListItem[]>([]);

  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [input, setInput] = useState("");
  const [loadingConv, setLoadingConv] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  const chatInputRef = useRef<HTMLInputElement>(null);
  const inlineInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const nestingLevels = useMemo(() => {
    if (!canvas) return {};
    return computeNestingLevels(canvas);
  }, [canvas]);

  const findNodeByNameOrId = useCallback((name?: string | null, id?: string | null) => {
    if (name) {
      const cleanName = name.trim().toLowerCase();
      const agent = canvas?.nodes?.agents?.find(
        (a) => a.name.trim().toLowerCase() === cleanName
      );
      if (agent) return agent;
      const tool = canvas?.nodes?.tools?.find(
        (t) => t.name.trim().toLowerCase() === cleanName
      );
      if (tool) return tool;
    }
    if (id) {
      const agent = canvas?.nodes?.agents?.find((a) => a.id === id);
      if (agent) return agent;
      const tool = canvas?.nodes?.tools?.find((t) => t.id === id);
      if (tool) return tool;
    }
    return null;
  }, [canvas]);

  const getMessageNestingLevel = useCallback((msg: Message) => {
    const node = findNodeByNameOrId(msg.agent_name, msg.node_id ?? undefined);
    if (node && nestingLevels[node.id] !== undefined) {
      return nestingLevels[node.id];
    }
    return 0;
  }, [findNodeByNameOrId, nestingLevels]);

  const loadSidebar = useCallback(async () => {
    if (!canvasId) return;
    try {
      const list = await listConversations(canvasId);
      setConversations(list);
    } catch (err) {
      console.error("Failed to load conversation list:", err);
    }
  }, [canvasId]);

  const {
    messages,
    setMessages,
    running,
    activeInterrupt,
    expandedTurns,
    collapsedSteps,
    connectAndRun,
    stopRun,
    handleSendHumanResponse,
    handleSendToolApproval,
    toggleExpand,
    toggleStepExpand,
  } = useChatWebSocket({
    conversation_id,
    loadSidebar,
    setConversationName,
    setConversations,
    chatInputRef,
    inlineInputRef,
    loadingConv,
  });

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Fetch all canvases on mount
  useEffect(() => {
    listCanvases()
      .then((list) => {
        setAllCanvases(list);
      })
      .catch((err) => console.error("Failed to load canvases list:", err));
  }, []);

  const queryCanvasId = searchParams.get("canvas");

  // Load conversation details or default canvas
  useEffect(() => {
    const initAndLoad = async () => {
      if (!conversation_id || conversation_id === "empty") {
        setMessages([]);
        setConversationName("Chat");
        
        if (queryCanvasId) {
          setCanvasId(queryCanvasId);
          try {
            const canvasData = await getCanvas(queryCanvasId);
            setCanvasName(canvasData.name);
            setCanvas(canvasData);
          } catch (err) {
            console.error("Failed to load canvas data for query param:", err);
          }
        } else if (allCanvases.length > 0) {
          const firstCanvasId = allCanvases[0].id;
          navigate(`/chat/empty?canvas=${firstCanvasId}`, { replace: true });
        }
        setLoadingConv(false);
        return;
      }

      setLoadingConv(true);
      setError(null);
      try {
        const conv = await getConversationById(conversation_id);
        const orderedMessages = [...(conv.messages ?? [])].sort(
          (a, b) =>
            new Date(a.created_at).getTime() -
            new Date(b.created_at).getTime()
        );
        setMessages(orderedMessages);
        setCanvasId(conv.canvas_id);
        setConversationName(conv.name);

        try {
          const canvasData = await getCanvas(conv.canvas_id);
          setCanvasName(canvasData.name);
          setCanvas(canvasData);
        } catch (err) {
          console.error("Failed to load canvas name:", err);
        }
      } catch (err: any) {
        setError("Failed to load conversation. It may have been deleted.");
        console.error("Failed to load conversation:", err);
      } finally {
        setLoadingConv(false);
      }
    };

    initAndLoad();
  }, [conversation_id, queryCanvasId, allCanvases, navigate, setMessages]);

  useEffect(() => {
    loadSidebar();
  }, [canvasId, loadSidebar]);

  const handleNewConversation = async () => {
    if (!canvasId) return;
    try {
      const conv = await createConversation(canvasId, "New Conversation");
      setConversations((prev) => [conv, ...prev]);
      navigate(`/chat/${conv.id}`);
    } catch (err) {
      console.error("Failed to create conversation:", err);
    }
  };

  const handleDeleteConversation = async (id: string) => {
    try {
      await deleteConversationById(id);
      setConversations((prev) => prev.filter((c) => c.id !== id));
      if (conversation_id === id) {
        navigate(`/chat/empty`);
      }
    } catch (err) {
      console.error("Failed to delete conversation:", err);
    }
    setDeleteConfirmId(null);
  };

  const handleExportConversation = async (e: React.MouseEvent, id: string, name: string) => {
    e.stopPropagation();
    try {
      if (!canvasId) return;
      setError(null);
      const blob = await exportConversationZip(canvasId, id);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const safeName = name.replace(/\s+/g, "_").replace(/\//g, "_");
      a.download = `conversation-${safeName}.zip`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      setError("Failed to export conversation.");
      console.error("Failed to export conversation:", err);
    }
  };

  const handleImportClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !canvasId) return;

    setError(null);
    try {
      const newConv = await importConversationZip(canvasId, file);
      setConversations((prev) => [newConv, ...prev]);
      navigate(`/chat/${newConv.id}`);
    } catch (err: any) {
      setError("Failed to import conversation. Please make sure the uploaded file is a valid conversation ZIP archive.");
      console.error("Failed to import conversation:", err);
    } finally {
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleSend = () => {
    console.log("handleSend called", { input, conversation_id, running });
    if (!input.trim() || !conversation_id || running) return;

    const prompt = input.trim();
    setInput("");
    connectAndRun(conversation_id, { prompt });
  };

  const { preTurnMessages, turns } = groupMessagesIntoTurns(messages);

  const isEmpty = !conversation_id || conversation_id === "empty";

  return (
    <div className="h-screen w-screen flex bg-[var(--color-base)] noise-bg relative overflow-hidden">
      <ChatSidebar
        sidebarCollapsed={sidebarCollapsed}
        setSidebarCollapsed={setSidebarCollapsed}
        theme={theme as "light" | "dark"}
        canvasId={canvasId}
        conversation_id={conversation_id}
        conversations={conversations}
        handleNewConversation={handleNewConversation}
        handleExportConversation={handleExportConversation}
        setDeleteConfirmId={setDeleteConfirmId}
        handleImportClick={handleImportClick}
        fileInputRef={fileInputRef}
        handleFileChange={handleFileChange}
      />

      {/* Right Main Chat Panel */}
      <main className="flex-1 h-full flex flex-col relative z-10 overflow-hidden">
        {/* Top Header */}
        <header className="h-12 border-b border-[var(--color-border-subtle)] bg-[var(--color-surface)] flex items-center justify-between px-6">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-[var(--color-text-tertiary)] uppercase tracking-wider">
              Chat session
            </span>
            <span className="text-xs text-[var(--color-text-tertiary)]">•</span>
            <span className="text-[13px] font-semibold text-[var(--color-text-primary)]">
              {conversationName || canvasName}
            </span>
          </div>

          <div className="flex items-center gap-4">
            {allCanvases.length > 0 && (
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-semibold text-[var(--color-text-tertiary)] uppercase tracking-wider">
                  Canvas:
                </span>
                <select
                  value={canvasId || ""}
                  onChange={(e) => {
                    const selectedId = e.target.value;
                    if (selectedId) {
                      navigate(`/chat/empty?canvas=${selectedId}`);
                    }
                  }}
                  disabled={!isEmpty}
                  title={!isEmpty ? "Cannot change canvas mid-conversation" : "Select canvas for chat"}
                  className="bg-[var(--color-surface)] border border-[var(--color-border-default)] rounded-lg px-2.5 py-1 text-xs font-semibold text-[var(--color-text-primary)] outline-none focus:border-[var(--color-accent)] disabled:opacity-60 disabled:cursor-not-allowed transition-all duration-200 cursor-pointer"
                >
                  {allCanvases.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
            {/* Theme toggle + account + logout (shared chrome) */}
            <AccountControls />
          </div>
        </header>

        {/* Main Content Area */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {error && (
            <div className="p-4 rounded-xl bg-[var(--color-danger-subtle)] border border-[var(--color-danger)]/20 text-[var(--color-danger)] flex items-start gap-3 animate-fade-in max-w-2xl mx-auto shadow-lg">
              <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="text-xs font-semibold">Error</p>
                <p className="text-xs opacity-90">{error}</p>
              </div>
            </div>
          )}

          {isEmpty ? (
            /* Empty State */
            <div className="h-full w-full flex flex-col items-center justify-center max-w-md mx-auto text-center space-y-5 animate-fade-in">
              <div className="w-16 h-16 rounded-2xl bg-[var(--color-accent-subtle)] border border-[var(--color-accent)]/30 flex items-center justify-center text-[var(--color-accent)] shadow-[0_4px_20px_rgba(20,184,166,0.15)]">
                <MessageSquare className="w-8 h-8" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-[var(--color-text-primary)]">
                  No Chat Active
                </h3>
                <p className="text-xs text-[var(--color-text-secondary)] mt-1.5 leading-relaxed">
                  Select a past session from the sidebar or start a new conversation to begin orchestrating your agent workflow.
                </p>
              </div>
              <button
                onClick={handleNewConversation}
                disabled={!canvasId}
                className="btn-primary px-5 py-2.5 shadow-lg shadow-[var(--color-accent-subtle)]"
              >
                <Plus className="w-4 h-4" />
                Start New Conversation
              </button>
            </div>
          ) : (
            /* Chat Messages Render */
            <div className="max-w-3xl mx-auto space-y-4">
              {loadingConv ? (
                <div className="flex justify-center py-12">
                  <div className="flex gap-1">
                    {[0, 1, 2].map((i) => (
                      <span
                        key={i}
                        className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent)] animate-bounce"
                        style={{ animationDelay: `${i * 0.15}s` }}
                      />
                    ))}
                  </div>
                </div>
              ) : (
                <>
                  {messages.length === 0 && !running && (
                    <div className="text-center py-20 text-[var(--color-text-tertiary)] text-xs font-light">
                      Send a message to start orchestrating your workflow.
                    </div>
                  )}

                  {preTurnMessages.map((msg) => (
                    <div
                      key={msg.id}
                      className="flex flex-col items-start"
                      style={{ animation: "staggerFadeIn 0.3s ease-out" }}
                    >
                      <div className="max-w-[85%] rounded-xl px-3.5 py-2.5 text-[13px] leading-relaxed bg-[var(--color-danger-subtle)] text-[var(--color-danger)] border border-[var(--color-danger)]/25 rounded-bl-sm">
                        {msg.content}
                      </div>
                    </div>
                  ))}

                  {turns.map((turn) => (
                    <MessageTurn
                      key={turn.id}
                      turn={turn}
                      running={running}
                      expandedTurns={expandedTurns}
                      toggleExpand={toggleExpand}
                      collapsedSteps={collapsedSteps}
                      toggleStepExpand={toggleStepExpand}
                      getMessageNestingLevel={getMessageNestingLevel}
                      activeInterrupt={activeInterrupt}
                      handleSendHumanResponse={handleSendHumanResponse}
                      handleSendToolApproval={handleSendToolApproval}
                      inlineInputRef={inlineInputRef}
                      renderMessageContent={renderMessageContent}
                    />
                  ))}

                  {running && (
                    <div className="flex items-start">
                      <div className="bg-[var(--color-elevated)] border border-[var(--color-border-subtle)] rounded-xl rounded-bl-sm px-3.5 py-2.5">
                        <div className="flex gap-1.5 items-center">
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
                    </div>
                  )}
                </>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input Bar */}
        {!isEmpty && (
          <div className="border-t border-[var(--color-border-subtle)] p-4 bg-[var(--color-surface)] flex justify-center">
            <div className="max-w-3xl w-full flex gap-3">
              <input
                ref={chatInputRef}
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                placeholder={activeInterrupt ? "Waiting for your response/approval above..." : running ? "Orchestrating workflow..." : "Message agents..."}
                disabled={(running && !activeInterrupt) || loadingConv}
                data-testid="chat-input"
                className="input-base flex-1 py-2.5 px-4 rounded-xl"
              />
              <button
                onClick={running ? stopRun : handleSend}
                disabled={!running && (!input.trim() || loadingConv)}
                data-testid={running ? "stop-button" : "send-button"}
                className={`px-4 py-2.5 rounded-xl text-white text-sm font-semibold transition-all duration-200 disabled:opacity-40 flex items-center justify-center shadow ${running
                  ? "bg-[var(--color-danger)] hover:bg-[var(--color-danger)]/90"
                  : "bg-[var(--color-accent)] hover:bg-[var(--color-accent-bright)] shadow-[var(--color-accent-subtle)]"
                  }`}
              >
                {running ? (
                  <Square className="w-3.5 h-3.5" />
                ) : (
                  <Send className="w-4 h-4" />
                )}
              </button>
            </div>
          </div>
        )}
      </main>

      {/* Delete Confirmation Modal */}
      {deleteConfirmId && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="w-full max-w-sm p-6 rounded-2xl bg-[var(--color-surface)] border border-[var(--color-border-strong)] shadow-2xl animate-fade-in">
            <h3 className="text-base font-semibold delete-modal-title mb-2">
              Delete Chat Session?
            </h3>
            <p className="text-xs text-[var(--color-text-secondary)] mb-6 leading-relaxed">
              Are you sure you want to delete this conversation session? This will permanently remove all message history. This action cannot be undone.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setDeleteConfirmId(null)}
                className="btn-secondary text-xs px-4 py-2"
              >
                Cancel
              </button>
              <button
                onClick={() => deleteConfirmId && handleDeleteConversation(deleteConfirmId)}
                className="btn-primary bg-[var(--color-danger)] hover:bg-red-600 text-white text-xs px-4 py-2"
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
