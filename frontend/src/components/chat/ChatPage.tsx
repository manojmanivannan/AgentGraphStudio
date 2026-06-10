import { useState, useRef, useEffect, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  Send,
  Plus,
  Trash2,
  MessageSquare,
  ChevronDown,
  ChevronRight,
  Home,
  Layout,
  Square,
  AlertCircle,
  FolderKanban,
  Activity,
} from "lucide-react";
import { useCanvasStore } from "@/store/canvasStore";
import { useThemeStore } from "@/store/themeStore";
import { ThemeToggle } from "@/components/ThemeToggle";
import {
  createConversation,
  listConversations,
  getConversationById,
  deleteConversationById,
  getCanvas,
} from "@/lib/api";
import type { ConversationSummary, Message, ExecutionEvent } from "@/types";

const WS_BASE = `ws://${import.meta.env.VITE_API_HOST || "localhost:8000"}`;


interface TurnGroup {
  id: string;
  userMessage: Message;
  steps: Message[];
  finalAnswer?: Message;
  isStreaming: boolean;
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
      } else {
        currentTurn.steps.push(msg);
      }
    } else {
      preTurnMessages.push(msg);
    }
  }

  return { preTurnMessages, turns };
}

export default function ChatPage() {
  const { conversation_id } = useParams<{ conversation_id: string }>();
  const navigate = useNavigate();

  const setActiveNodeId = useCanvasStore((s) => s.setActiveNodeId);
  const theme = useThemeStore((s) => s.theme);

  const [canvasId, setCanvasId] = useState<string | null>(null);
  const [canvasName, setCanvasName] = useState<string>("Canvas");
  const [conversationName, setConversationName] = useState<string>("Chat");
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [loadingConv, setLoadingConv] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedTurns, setExpandedTurns] = useState<Set<string>>(() => new Set());
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const localMessagesRef = useRef<Message[]>([]);

  useEffect(() => {
    localMessagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Reset expand state when switching conversations
  useEffect(() => {
    setExpandedTurns(new Set());
  }, [conversation_id]);

  // Support loading canvas_id from query param for empty state
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const urlCanvasId = params.get("canvas");
    if (urlCanvasId) {
      setCanvasId(urlCanvasId);
      // Fetch canvas name
      getCanvas(urlCanvasId)
        .then((canvasData) => setCanvasName(canvasData.name))
        .catch((err) => console.error("Failed to load canvas name from query param:", err));
    }
  }, []);

  // Load conversation details
  useEffect(() => {
    if (!conversation_id || conversation_id === "empty") {
      setMessages([]);
      return;
    }

    const loadConv = async () => {
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

        // Fetch canvas name
        try {
          const canvasData = await getCanvas(conv.canvas_id);
          setCanvasName(canvasData.name);
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

    loadConv();
  }, [conversation_id]);

  // Load sidebar conversations once we have a canvas_id
  const loadSidebar = useCallback(async () => {
    if (!canvasId) return;
    try {
      const list = await listConversations(canvasId);
      setConversations(list);
    } catch (err) {
      console.error("Failed to load conversation list:", err);
    }
  }, [canvasId]);

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

  const toggleExpand = useCallback((turnId: string) => {
    setExpandedTurns((prev) => {
      const next = new Set(prev);
      if (next.has(turnId)) {
        next.delete(turnId);
      } else {
        next.add(turnId);
      }
      return next;
    });
  }, []);

  const addMessageLocal = (msg: Message) => {
    setMessages((prev) => [...prev, msg]);
  };

  const handleSend = () => {
    if (!input.trim() || !conversation_id || running) return;

    const prompt = input.trim();
    setInput("");

    const connectAndRun = async (convId: string) => {
      const userMsg: Message = {
        id: crypto.randomUUID(),
        conversation_id: convId,
        role: "user",
        content: prompt,
        created_at: new Date().toISOString(),
      };
      addMessageLocal(userMsg);

      setRunning(true);
      setActiveNodeId(null);

      const ws = new WebSocket(`${WS_BASE}/ws/conversations/${convId}/run`);
      wsRef.current = ws;

      ws.onopen = () => {
        ws.send(JSON.stringify({ prompt }));
      };

      const refreshConversationName = async () => {
        if (!conversation_id) return;
        try {
          const updated = await getConversationById(conversation_id);
          setConversationName(updated.name);
          setConversations((prev) =>
            prev.map((c) =>
              c.id === updated.id ? { ...c, name: updated.name } : c
            )
          );
        } catch (err) {
          console.error("Failed to refresh conversation name:", err);
        }
      };

      ws.onmessage = (evt) => {
        const event = JSON.parse(evt.data) as ExecutionEvent;

        if (event.type === "conversation_renamed") {
          setConversations((prev) =>
            prev.map((c) =>
              c.id === event.conversation_id
                ? { ...c, name: event.name }
                : c
            )
          );
          if (convId === conversation_id) {
            setConversationName(event.name);
          }
          loadSidebar();
          return;
        }

        if (event.type === "run_complete") {
          setRunning(false);
          setActiveNodeId(null);
          loadSidebar(); // Refresh sidebar order since conversation updated
          refreshConversationName();
          return;
        }

        if (event.type === "error") {
          const errMsg: Message = {
            id: crypto.randomUUID(),
            conversation_id: convId,
            role: "system",
            content: event.message,
            agent_name: event.agent ?? null,
            node_id: event.node_id ?? null,
            event_type: "error",
            created_at: new Date().toISOString(),
          };
          addMessageLocal(errMsg);
          setRunning(false);
          setActiveNodeId(null);
          return;
        }

        if (event.type === "warning") {
          const warnMsg: Message = {
            id: crypto.randomUUID(),
            conversation_id: convId,
            role: "system",
            content: event.message,
            agent_name: event.agent ?? null,
            node_id: event.node_id ?? null,
            event_type: "warning",
            created_at: new Date().toISOString(),
          };
          addMessageLocal(warnMsg);
        }

        if (event.node_id) {
          setActiveNodeId(event.node_id);
        }

        if (event.type === "final_answer") {
          const msg: Message = {
            id: crypto.randomUUID(),
            conversation_id: convId,
            role: "assistant",
            content: event.content,
            agent_name: event.agent ?? null,
            node_id: event.node_id ?? null,
            event_type: "final_answer",
            created_at: new Date().toISOString(),
          };
          addMessageLocal(msg);
        }

        if (event.type === "thought") {
          const msg: Message = {
            id: crypto.randomUUID(),
            conversation_id: convId,
            role: "assistant",
            content: event.content,
            agent_name: event.agent,
            node_id: event.node_id ?? null,
            event_type: "thought",
            created_at: new Date().toISOString(),
          };
          addMessageLocal(msg);
        }

        if (event.type === "handoff") {
          const msg: Message = {
            id: crypto.randomUUID(),
            conversation_id: convId,
            role: "system",
            content: `Delegating to ${event.to}...`,
            agent_name: event.from,
            node_id: event.node_id ?? null,
            event_type: "handoff",
            created_at: new Date().toISOString(),
          };
          addMessageLocal(msg);
        }

        if (event.type === "tool_result") {
          const msg: Message = {
            id: crypto.randomUUID(),
            conversation_id: convId,
            role: "assistant",
            content: event.output,
            agent_name: event.tool?.replace("transfer_to_", "") ?? event.agent,
            node_id: event.node_id ?? null,
            event_type: "tool_result",
            created_at: new Date().toISOString(),
          };
          addMessageLocal(msg);
        }
      };

      ws.onerror = () => {
        addMessageLocal({
          id: crypto.randomUUID(),
          conversation_id: convId,
          role: "system",
          content: "WebSocket connection failed. Is the backend running?",
          event_type: "error",
          created_at: new Date().toISOString(),
        });
        setRunning(false);
        setActiveNodeId(null);
      };

      ws.onclose = (ev) => {
        if (wsRef.current === ws) wsRef.current = null;
        if (ev.code !== 1000 && ev.code !== 1005) {
          addMessageLocal({
            id: crypto.randomUUID(),
            conversation_id: convId,
            role: "system",
            content: `Connection closed unexpectedly (code ${ev.code}).`,
            event_type: "error",
            created_at: new Date().toISOString(),
          });
        }
        setRunning(false);
        setActiveNodeId(null);
      };
    };

    connectAndRun(conversation_id);
  };

  const stopRun = () => {
    wsRef.current?.close();
    setRunning(false);
    setActiveNodeId(null);
  };

  const { preTurnMessages, turns } = groupMessagesIntoTurns(messages);

  const isEmpty = !conversation_id || conversation_id === "empty";

  return (
    <div className="h-screen w-screen flex bg-[var(--color-base)] noise-bg relative overflow-hidden">
      {/* Left Sidebar Panel */}
      <aside className="w-64 h-full border-r border-[var(--color-border-subtle)] bg-[var(--color-surface)] flex flex-col z-20">
        {/* Sidebar Header */}
        <div className="p-4 border-b border-[var(--color-border-subtle)] flex flex-col gap-2">
          <div className="flex items-center gap-2 mb-2">
            <img
              src={theme === "dark" ? "/agent_graph_studio_logo_white.png" : "/agent_graph_studio_logo_dark.png"}
              alt="Logo"
              className="h-6 w-auto object-contain shrink-0"
            />
            <span className="font-bold text-[14px] tracking-tight text-[var(--color-text-primary)]">
              AgentGraph Studio
            </span>
          </div>

          <div className="space-y-1">
            <Link
              to="/"
              className="flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-elevated)] transition-colors"
              title="Home"
            >
              <Home className="w-4 h-4 text-[var(--color-text-tertiary)]" />
              Home
            </Link>
            {canvasId && (
              <Link
                to={`/canvas/${canvasId}`}
                className="flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-elevated)] transition-colors"
                title="Canvas Editor"
              >
                <Layout className="w-4 h-4 text-[var(--color-text-tertiary)]" />
                Visual Canvas
              </Link>
            )}
            <button
              className="w-full flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-[var(--color-elevated)] text-[var(--color-text-primary)] border border-[var(--color-border-default)] transition-colors text-left"
            >
              <MessageSquare className="w-4 h-4 text-[var(--color-text-tertiary)]" />
              Agent Chat
            </button>
            <button
              onClick={() => window.open("/mlflow/", "_blank")}
              className="w-full flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-elevated)] transition-colors text-left cursor-pointer"
            >
              <Activity className="w-4 h-4 text-[var(--color-text-tertiary)]" />
              Observability
            </button>
          </div>
        </div>

        {/* Sidebar Middle - Conversations List */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          <div className="px-2 py-1.5 text-[10px] font-semibold text-[var(--color-text-tertiary)] uppercase tracking-[0.08em]">
            Recent Chats
          </div>
          {conversations.length === 0 && (
            <div className="px-3 py-6 text-xs text-[var(--color-text-tertiary)] text-center font-light">
              No chats found for this canvas.
            </div>
          )}
          {conversations.map((c) => {
            const isActive = c.id === conversation_id;
            return (
              <div
                key={c.id}
                className={`group flex items-center justify-between px-2 py-1.5 rounded-lg cursor-pointer transition-all duration-150 ${isActive
                  ? "bg-[var(--color-elevated)] border border-[var(--color-border-default)] text-[var(--color-text-primary)]"
                  : "hover:bg-[var(--color-overlay)]/40 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
                  }`}
                onClick={() => navigate(`/chat/${c.id}`)}
              >
                <div className="flex items-center gap-2 truncate flex-1">
                  <MessageSquare className="w-3.5 h-3.5 text-[var(--color-text-tertiary)] shrink-0" />
                  <span className="text-xs truncate font-medium">{c.name}</span>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setDeleteConfirmId(c.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 p-1 text-[var(--color-text-tertiary)] hover:text-[var(--color-danger)] hover:bg-[var(--color-danger-subtle)] rounded transition-all duration-150"
                  title="Delete conversation"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            );
          })}
        </div>

        {/* Sidebar Bottom - Start New Conversation */}
        <div className="p-3 border-t border-[var(--color-border-subtle)] bg-[var(--color-inset)]">
          <button
            onClick={handleNewConversation}
            disabled={!canvasId}
            className="w-full btn-primary flex items-center justify-center gap-1.5 py-2 text-xs"
          >
            <Plus className="w-3.5 h-3.5" />
            New Conversation
          </button>
        </div>
      </aside>

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

          <div className="flex items-center gap-3">
            <ThemeToggle className="hover:bg-[var(--color-elevated)]" />
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

                  {turns.map((turn) => {
                    const isStreaming = turn.isStreaming && running;
                    const isExpanded = expandedTurns.has(turn.id);
                    const hasSteps = turn.steps.length > 0;

                    return (
                      <div key={turn.id} className="space-y-3">
                        {/* User Message */}
                        <div
                          className="flex flex-col items-end"
                          style={{ animation: "staggerFadeIn 0.3s ease-out" }}
                        >
                          <div className="max-w-[85%] rounded-2xl px-4 py-2.5 text-[13px] leading-relaxed bg-[var(--color-accent)] text-[var(--color-text-inverse)] rounded-br-sm shadow-md font-medium">
                            {turn.userMessage.content}
                          </div>
                        </div>

                        {/* Steps toggle */}
                        {!isStreaming && hasSteps && (
                          <button
                            onClick={() => toggleExpand(turn.id)}
                            className="flex items-center gap-1.5 text-[11px] text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)] transition-colors cursor-pointer px-1 font-semibold"
                          >
                            {isExpanded ? (
                              <>
                                <ChevronDown className="w-3.5 h-3.5" />
                                <span>Hide execution steps</span>
                              </>
                            ) : (
                              <>
                                <ChevronRight className="w-3.5 h-3.5" />
                                <span>
                                  Show {turn.steps.length} execution step
                                  {turn.steps.length !== 1 && "s"}
                                </span>
                              </>
                            )}
                          </button>
                        )}

                        {/* Steps Container */}
                        {(isStreaming || isExpanded) && hasSteps && (
                          <div className="ml-3 pl-3 border-l-2 border-[var(--color-border-subtle)] space-y-2.5">
                            {turn.steps.map((stepMsg) => {
                              const isThought = stepMsg.event_type === "thought";
                              const isHandoff = stepMsg.event_type === "handoff";
                              const isToolResult = stepMsg.event_type === "tool_result";
                              const isError = stepMsg.event_type === "error";
                              const isSubAnswer = stepMsg.event_type === "final_answer";
                              const isWarning = stepMsg.event_type === "warning";

                              return (
                                <div
                                  key={stepMsg.id}
                                  className="flex flex-col items-start"
                                  style={{ animation: "staggerFadeIn 0.3s ease-out" }}
                                >
                                  {stepMsg.agent_name && !isHandoff && !isError && !isWarning && (
                                    <span className="text-[10px] text-[var(--color-text-tertiary)] mb-0.5 px-1 font-semibold tracking-wide">
                                      {stepMsg.agent_name}
                                      {stepMsg.event_type &&
                                        stepMsg.event_type !== "final_answer" &&
                                        ` · ${stepMsg.event_type}`}
                                    </span>
                                  )}
                                  <div
                                    className={`max-w-[85%] rounded-xl px-3 py-2 text-[12px] leading-relaxed shadow-sm ${isHandoff
                                      ? "bg-[var(--color-info-subtle)] text-[var(--color-info)] border border-[var(--color-info)]/20 rounded-bl-sm"
                                      : isError
                                        ? "bg-[var(--color-danger-subtle)] text-[var(--color-danger)] border border-[var(--color-danger)]/20 rounded-bl-sm"
                                        : isWarning
                                          ? "bg-[var(--color-warning-subtle)] text-[var(--color-warning)] border border-[var(--color-warning)]/20 rounded-bl-sm"
                                          : isThought
                                            ? "bg-[var(--color-agent-subtle)] text-[var(--color-agent)] border border-[var(--color-agent)]/20 rounded-bl-sm font-mono whitespace-pre-wrap text-[11px]"
                                            : isToolResult
                                              ? "bg-[var(--color-success-subtle)] text-[var(--color-success)] border border-[var(--color-success)]/20 rounded-bl-sm font-mono"
                                              : isSubAnswer
                                                ? "bg-[var(--color-elevated)] text-[var(--color-text-secondary)] border border-[var(--color-border-subtle)] rounded-bl-sm"
                                                : "bg-[var(--color-elevated)] text-[var(--color-text-primary)] border border-[var(--color-border-subtle)] rounded-bl-sm"
                                      }`}
                                  >
                                    {stepMsg.content}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}

                        {/* Final Answer */}
                        {turn.finalAnswer && (
                          <div
                            className="flex flex-col items-start"
                            style={{ animation: "staggerFadeIn 0.3s ease-out" }}
                          >
                            {turn.finalAnswer.agent_name && (
                              <span className="text-[10px] text-[var(--color-text-tertiary)] mb-0.5 px-1 font-semibold tracking-wide">
                                {turn.finalAnswer.agent_name}
                              </span>
                            )}
                            <div className="max-w-[85%] rounded-2xl px-4 py-3 text-[13px] leading-relaxed bg-[var(--color-surface)] text-[var(--color-text-primary)] border border-[var(--color-border-default)] rounded-bl-sm shadow-md">
                              {turn.finalAnswer.content}
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}

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
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                placeholder="Message agents..."
                disabled={running || loadingConv}
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
            <h3 className="text-base font-semibold text-[var(--color-text-primary)] mb-2">
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
