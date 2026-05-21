import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Plus, Trash2, MessageSquare, ChevronDown, ChevronRight } from "lucide-react";
import { useCanvasStore } from "@/store/canvasStore";
import {
  createConversation,
  listConversations,
  getConversation,
  deleteConversation,
} from "@/lib/api";
import type { ConversationSummary, Message, ExecutionEvent } from "@/types";

const WS_BASE = `ws://${import.meta.env.VITE_API_HOST || "localhost:8000"}`;

export function ChatPanel() {
  const canvasId = useCanvasStore((s) => s.canvasId);
  const setActiveNodeId = useCanvasStore((s) => s.setActiveNodeId);

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

  return (
    <div className="w-96 h-full border-l border-gray-200 bg-white flex flex-col">
      <div className="border-b border-gray-200 p-3">
        <div className="relative">
          <button
            onClick={() => setSelectorOpen(!selectorOpen)}
            data-testid="conversation-selector"
            className="w-full flex items-center justify-between px-3 py-2 text-sm border border-gray-200 rounded-lg hover:border-gray-300"
          >
            <span className="text-gray-700 truncate flex-1 text-left">
              {activeConvId
                ? conversations.find((c) => c.id === activeConvId)?.name ??
                  "Conversation"
                : "Select conversation"}
            </span>
            <ChevronDown className="w-4 h-4 text-gray-400 ml-2" />
          </button>

          {selectorOpen && (
            <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-50 max-h-64 overflow-y-auto">
              <button
                onClick={handleNewConversation}
                data-testid="new-conversation-button"
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-indigo-600 hover:bg-indigo-50 border-b border-gray-100"
              >
                <Plus className="w-4 h-4" />
                New Conversation
              </button>
              {conversations.length === 0 && (
                <div className="px-3 py-4 text-sm text-gray-400 text-center">
                  No conversations yet
                </div>
              )}
              {conversations.map((c) => (
                <div
                  key={c.id}
                  className="flex items-center px-3 py-2 hover:bg-gray-50 cursor-pointer"
                >
                  <button
                    className="flex items-center gap-2 flex-1 text-sm text-gray-700 text-left"
                    onClick={() => {
                      loadConversation(c.id);
                      setSelectorOpen(false);
                    }}
                  >
                    <MessageSquare className="w-4 h-4 text-gray-400" />
                    <span className="truncate">{c.name}</span>
                    <span
                      className={`text-[10px] ml-auto px-1.5 py-0.5 rounded-full ${
                        c.status === "active"
                          ? "bg-green-100 text-green-600"
                          : "bg-gray-100 text-gray-500"
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
                    className="ml-2 p-1 text-gray-400 hover:text-red-500 rounded"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 && !running && (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm">
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
          >
            {msg.agent_name && msg.role !== "user" && !isHandoff && !isAgentStart && (
              <span className="text-[10px] text-gray-400 mb-0.5 px-1">
                {msg.agent_name}
                {msg.event_type === "tool_result" ? "" : msg.event_type && ` · ${msg.event_type}`}
              </span>
            )}
            <div
              className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                msg.role === "user"
                  ? "bg-indigo-600 text-white"
                  : isHandoff || isAgentStart
                  ? "bg-blue-50 text-blue-600 border border-blue-200"
                  : msg.role === "system"
                  ? "bg-red-50 text-red-600 border border-red-200"
                  : isThought
                  ? "bg-purple-50 text-purple-700 border border-purple-200 text-xs"
                  : isToolResult
                  ? "bg-green-50 text-green-700 border border-green-200"
                  : "bg-gray-100 text-gray-800"
              }`}
            >
              {(isHandoff || isAgentStart) ? (
                <div className="flex items-center gap-2 text-xs">
                  <span>{msg.content}</span>
                </div>
              ) : isThought && isCollapsed ? (
                <button
                  onClick={() => toggleCollapse(msg.id)}
                  className="flex items-center gap-1 text-purple-500 hover:text-purple-700 cursor-pointer w-full text-left"
                >
                  <ChevronRight className="w-3 h-3 flex-shrink-0" />
                  <span>Thinking...</span>
                </button>
              ) : isThought ? (
                <div>
                  <button
                    onClick={() => toggleCollapse(msg.id)}
                    className="flex items-center gap-1 text-purple-500 hover:text-purple-700 cursor-pointer mb-1"
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
            <div className="bg-gray-100 rounded-lg px-3 py-2">
              <div className="flex gap-1">
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:0.1s]" />
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:0.2s]" />
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <div className="border-t border-gray-200 p-3">
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
            className="flex-1 px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-400 focus:border-indigo-400 disabled:opacity-50"
          />
          <button
            onClick={running ? stopRun : handleSend}
            disabled={!running && (!input.trim() || !canvasId)}
            data-testid={running ? "stop-button" : "send-button"}
            className={`px-3 py-2 rounded-lg text-white text-sm font-medium transition-colors disabled:opacity-50 ${
              running
                ? "bg-red-600 hover:bg-red-700"
                : "bg-indigo-600 hover:bg-indigo-700"
            }`}
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
