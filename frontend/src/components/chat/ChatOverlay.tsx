import { useState, useRef, useEffect, useCallback } from "react";
import {
  Send,
  Plus,
  Trash2,
  MessageSquare,
  ChevronDown,
  ChevronRight,
  X,
  Square,
} from "lucide-react";
import { useCanvasStore } from "@/store/canvasStore";
import { OverlayPanel } from "@/components/layout/OverlayPanel";
import {
  createConversation,
  listConversations,
  getConversation,
  deleteConversation,
} from "@/lib/api";
import type { ConversationSummary, Message, ExecutionEvent } from "@/types";

const WS_BASE = `ws://${import.meta.env.VITE_API_HOST || "localhost:8000"}`;

export function ChatOverlay() {
  const canvasId = useCanvasStore((s) => s.canvasId);
  const setActiveNodeId = useCanvasStore((s) => s.setActiveNodeId);
  const chatOpen = useCanvasStore((s) => s.chatOpen);
  const toggleChat = useCanvasStore((s) => s.toggleChat);
  const selectedNodeId = useCanvasStore((s) => s.selectedNodeId);

  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [selectorOpen, setSelectorOpen] = useState(false);
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set());

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const localMessagesRef = useRef<Message[]>([]);

  useEffect(() => {
    if (canvasId) {
      listConversations(canvasId)
        .then(setConversations)
        .catch(() => {});
    } else {
      setConversations([]);
      setActiveConvId(null);
      setMessages([]);
    }
  }, [canvasId]);

  useEffect(() => {
    localMessagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const loadConversation = async (convId: string) => {
    if (!canvasId) return;
    try {
      const conv = await getConversation(canvasId, convId);
      setMessages(conv.messages ?? []);
      setActiveConvId(convId);
    } catch {
      // conversation may have been deleted
    }
  };

  const handleNewConversation = async () => {
    if (!canvasId) return;
    try {
      const conv = await createConversation(canvasId, "New Conversation");
      setConversations((prev) => [conv, ...prev]);
      setActiveConvId(conv.id);
      setMessages([]);
    } catch {
      // ignore
    }
    setSelectorOpen(false);
  };

  const handleDeleteConversation = async (convId: string) => {
    if (!canvasId) return;
    try {
      await deleteConversation(canvasId, convId);
      setConversations((prev) => prev.filter((c) => c.id !== convId));
      if (activeConvId === convId) {
        setActiveConvId(null);
        setMessages([]);
      }
    } catch {
      // ignore
    }
  };

  const toggleCollapse = useCallback((msgId: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(msgId)) {
        next.delete(msgId);
      } else {
        next.add(msgId);
      }
      return next;
    });
  }, []);

  useEffect(() => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      for (const msg of messages) {
        if (msg.event_type === "thought") {
          next.add(msg.id);
        }
      }
      return next;
    });
  }, [messages]);

  const addMessageLocal = (msg: Message) => {
    setMessages((prev) => [...prev, msg]);
    if (msg.event_type === "thought") {
      setCollapsed((prev) => new Set(prev).add(msg.id));
    }
  };

  const handleSend = () => {
    if (!input.trim() || !canvasId || running) return;

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

      ws.onmessage = (evt) => {
        const event = JSON.parse(evt.data) as ExecutionEvent;

        if (event.type === "run_complete") {
          setRunning(false);
          setActiveNodeId(null);
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

        if (event.type === "agent_start") {
          const msg: Message = {
            id: crypto.randomUUID(),
            conversation_id: convId,
            role: "system",
            content: `${event.agent} is working...`,
            agent_name: event.agent,
            node_id: event.node_id ?? null,
            event_type: "agent_start",
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
        setRunning(false);
        setActiveNodeId(null);
      };

      ws.onclose = () => {
        if (wsRef.current === ws) wsRef.current = null;
        setRunning(false);
        setActiveNodeId(null);
      };
    };

    if (activeConvId) {
      connectAndRun(activeConvId);
    } else {
      createConversation(canvasId, "New Conversation")
        .then((conv) => {
          setConversations((prev) => [conv, ...prev]);
          setActiveConvId(conv.id);
          connectAndRun(conv.id);
        })
        .catch(() => {});
    }
  };

  const stopRun = () => {
    wsRef.current?.close();
    setRunning(false);
    setActiveNodeId(null);
  };

  // Properties panel offset: if a node is selected, chat shifts left by 320px
  const offsetRight = selectedNodeId ? 320 : 0;

  return (
    <OverlayPanel
      open={chatOpen}
      width={400}
      offsetRight={offsetRight}
      onClose={toggleChat}
      data-testid="chat-panel"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-[var(--color-border-subtle)]">
        <span className="text-[11px] font-semibold text-[var(--color-text-tertiary)] uppercase tracking-[0.08em]">
          Conversation
        </span>
        <button
          onClick={toggleChat}
          data-testid="chat-close"
          className="p-1 text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)] rounded-md hover:bg-[var(--color-elevated)] transition-all duration-150"
          title="Close chat"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Conversation selector */}
      <div className="border-b border-[var(--color-border-subtle)] p-3">
        <div className="relative">
          <button
            onClick={() => setSelectorOpen(!selectorOpen)}
            data-testid="conversation-selector"
            className="w-full flex items-center justify-between px-3 py-2 text-[13px] border border-[var(--color-border-default)] rounded-lg hover:border-[var(--color-border-strong)] bg-[var(--color-base)] transition-colors"
          >
            <span className="text-[var(--color-text-secondary)] truncate flex-1 text-left">
              {activeConvId
                ? conversations.find((c) => c.id === activeConvId)?.name ??
                  "Conversation"
                : "Select conversation"}
            </span>
            <ChevronDown className="w-3.5 h-3.5 text-[var(--color-text-tertiary)] ml-2" />
          </button>

          {selectorOpen && (
            <div className="absolute top-full left-0 right-0 mt-1 bg-[var(--color-elevated)] border border-[var(--color-border-default)] rounded-lg shadow-[0_8px_32px_-8px_rgba(0,0,0,0.6)] z-50 max-h-64 overflow-y-auto">
              <button
                onClick={handleNewConversation}
                data-testid="new-conversation-button"
                className="w-full flex items-center gap-2 px-3 py-2.5 text-[13px] text-[var(--color-accent)] hover:bg-[var(--color-accent-subtle)] border-b border-[var(--color-border-subtle)] transition-colors"
              >
                <Plus className="w-3.5 h-3.5" />
                New Conversation
              </button>
              {conversations.length === 0 && (
                <div className="px-3 py-4 text-[12px] text-[var(--color-text-tertiary)] text-center">
                  No conversations yet
                </div>
              )}
              {conversations.map((c) => (
                <div
                  key={c.id}
                  className="flex items-center px-3 py-2 hover:bg-[var(--color-overlay)] cursor-pointer transition-colors"
                >
                  <button
                    className="flex items-center gap-2 flex-1 text-[13px] text-[var(--color-text-secondary)] text-left hover:text-[var(--color-text-primary)]"
                    onClick={() => {
                      loadConversation(c.id);
                      setSelectorOpen(false);
                    }}
                  >
                    <MessageSquare className="w-3.5 h-3.5 text-[var(--color-text-tertiary)]" />
                    <span className="truncate">{c.name}</span>
                    <span
                      className={`text-[10px] ml-auto px-1.5 py-0.5 rounded-md font-medium ${
                        c.status === "active"
                          ? "bg-[var(--color-success-subtle)] text-[var(--color-success)]"
                          : "bg-[var(--color-elevated)] text-[var(--color-text-tertiary)]"
                      }`}
                    >
                      {c.status}
                    </span>
                  </button>
                  <button
                    data-testid="delete-conversation-button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteConversation(c.id);
                    }}
                    className="ml-2 p-1 text-[var(--color-text-tertiary)] hover:text-[var(--color-danger)] rounded-md hover:bg-[var(--color-danger-subtle)] transition-all duration-150"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 && !running && (
          <div className="flex items-center justify-center h-full text-[var(--color-text-tertiary)] text-[12px]">
            {activeConvId
              ? "Send a message to start"
              : "Select or create a conversation"}
          </div>
        )}

        {messages.map((msg) => {
          const isThought = msg.event_type === "thought";
          const isCollapsed = collapsed.has(msg.id);
          const isHandoff = msg.event_type === "handoff";
          const isToolResult = msg.event_type === "tool_result";
          const isAgentStart = msg.event_type === "agent_start";

          return (
            <div
              key={msg.id}
              className={`flex flex-col ${
                msg.role === "user" ? "items-end" : "items-start"
              }`}
              style={{ animation: "staggerFadeIn 0.3s ease-out" }}
            >
              {msg.agent_name && msg.role !== "user" && !isHandoff && !isAgentStart && (
                <span className="text-[10px] text-[var(--color-text-tertiary)] mb-1 px-1 font-medium">
                  {msg.agent_name}
                  {msg.event_type === "tool_result"
                    ? ""
                    : msg.event_type && ` · ${msg.event_type}`}
                </span>
              )}
              <div
                className={`max-w-[85%] rounded-xl px-3 py-2.5 text-[13px] leading-relaxed ${
                  msg.role === "user"
                    ? "bg-[var(--color-accent)] text-[var(--color-text-inverse)] rounded-br-sm"
                    : isHandoff || isAgentStart
                    ? "bg-[var(--color-info-subtle)] text-[var(--color-info)] border border-[var(--color-info)]/20 rounded-bl-sm"
                    : msg.role === "system"
                    ? "bg-[var(--color-danger-subtle)] text-[var(--color-danger)] border border-[var(--color-danger)]/20 rounded-bl-sm"
                    : isThought
                    ? "bg-[var(--color-agent-subtle)] text-[var(--color-agent)] border border-[var(--color-agent)]/20 text-[12px] rounded-bl-sm"
                    : isToolResult
                    ? "bg-[var(--color-success-subtle)] text-[var(--color-success)] border border-[var(--color-success)]/20 rounded-bl-sm"
                    : "bg-[var(--color-elevated)] text-[var(--color-text-primary)] border border-[var(--color-border-subtle)] rounded-bl-sm"
                }`}
              >
                {isHandoff || isAgentStart ? (
                  <div className="flex items-center gap-2 text-[12px]">
                    <span>{msg.content}</span>
                  </div>
                ) : isThought && isCollapsed ? (
                  <button
                    onClick={() => toggleCollapse(msg.id)}
                    className="flex items-center gap-1 text-[var(--color-agent)] hover:text-[var(--color-agent)]/80 cursor-pointer w-full text-left"
                  >
                    <ChevronRight className="w-3 h-3 flex-shrink-0" />
                    <span className="text-[11px]">Thinking...</span>
                  </button>
                ) : isThought ? (
                  <div>
                    <button
                      onClick={() => toggleCollapse(msg.id)}
                      className="flex items-center gap-1 text-[var(--color-agent)] hover:text-[var(--color-agent)]/80 cursor-pointer mb-1"
                    >
                      <ChevronDown className="w-3 h-3 flex-shrink-0" />
                      <span className="text-[10px]">Hide thought</span>
                    </button>
                    {msg.content}
                  </div>
                ) : (
                  msg.content
                )}
              </div>
            </div>
          );
        })}

        {running && (
          <div className="flex items-start">
            <div className="bg-[var(--color-elevated)] border border-[var(--color-border-subtle)] rounded-xl rounded-bl-sm px-3 py-2.5">
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

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t border-[var(--color-border-subtle)] p-3">
        <div className="flex gap-2">
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
            placeholder="Type a message..."
            disabled={running || !canvasId}
            data-testid="chat-input"
            className="input-base flex-1"
          />
          <button
            onClick={running ? stopRun : handleSend}
            disabled={!running && (!input.trim() || !canvasId)}
            data-testid={running ? "stop-button" : "send-button"}
            className={`px-3 py-2 rounded-lg text-white text-sm font-medium transition-all duration-200 disabled:opacity-40 flex items-center justify-center ${
              running
                ? "bg-[var(--color-danger)] hover:bg-[var(--color-danger)]/90"
                : "bg-[var(--color-accent)] hover:bg-[var(--color-accent-bright)]"
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
    </OverlayPanel>
  );
}