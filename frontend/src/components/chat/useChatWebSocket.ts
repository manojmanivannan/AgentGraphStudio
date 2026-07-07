/**
 * @fileoverview Custom hook for managing the WebSocket connection, chat state,
 * and ReAct execution loop events for a specific conversation.
 *
 * Provides message tracking, connection handling, automatic reconnection, and
 * parsing of backend execution events (thoughts, tool calls, final answers, HITL).
 */

import { useState, useRef, useEffect, useCallback } from "react";
import { useCanvasStore } from "@/store/canvasStore";
import {
  getActiveRun,
  abortRun,
  submitInterruptResponse,
  getConversationById,
} from "@/lib/api";
import type { Message, ExecutionEvent, ConversationSummary } from "@/types";
import { executionEventToMessage } from "./executionEventMessage";

const useProxyMode = ((import.meta.env.VITE_USE_PROXY as string | undefined)?.trim() || "").toLowerCase() === "true";
const configuredWsHost = (import.meta.env.VITE_API_HOST as string | undefined)?.trim();
const fallbackWsBase = configuredWsHost
  ? /^wss?:\/\//.test(configuredWsHost)
    ? configuredWsHost
    : `ws://${configuredWsHost}`
  : "ws://localhost:8000";
const WS_BASE = useProxyMode
  ? (typeof window !== "undefined"
      ? `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`
      : "ws://localhost:5173")
  : fallbackWsBase;

interface UseChatWebSocketProps {
  conversation_id?: string;
  loadSidebar: () => void;
  setConversationName: (name: string) => void;
  setConversations: React.Dispatch<React.SetStateAction<ConversationSummary[]>>;
  chatInputRef: React.RefObject<HTMLInputElement | null>;
  inlineInputRef: React.RefObject<HTMLInputElement | null>;
  loadingConv: boolean;
}

export function useChatWebSocket({
  conversation_id,
  loadSidebar,
  setConversationName,
  setConversations,
  chatInputRef,
  inlineInputRef,
  loadingConv,
}: UseChatWebSocketProps) {
  const setActiveNodeId = useCanvasStore((s) => s.setActiveNodeId);

  const [messages, setMessages] = useState<Message[]>([]);
  const [running, setRunning] = useState(false);
  const [expandedTurns, setExpandedTurns] = useState<Set<string>>(() => new Set());
  const [collapsedSteps, setCollapsedSteps] = useState<Set<string>>(() => new Set());
  const [activeInterrupt, setActiveInterrupt] = useState<{
    type: "human_input" | "tool_approval";
    request_id: string;
    message_id: string;
    question?: string;
    tool?: string;
    args?: Record<string, unknown>;
  } | null>(null);

  const runningRef = useRef(running);
  useEffect(() => {
    runningRef.current = running;
  }, [running]);

  const wsRef = useRef<WebSocket | null>(null);
  const activeRunIdRef = useRef<string | null>(null);
  const lastSequenceRef = useRef<number>(0);
  const reconnectTimerRef = useRef<number | null>(null);
  const manualStopRef = useRef<boolean>(false);

  const resetLiveRunTracking = useCallback(() => {
    activeRunIdRef.current = null;
    lastSequenceRef.current = 0;
    manualStopRef.current = false;
    if (reconnectTimerRef.current !== null) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const addMessageLocal = useCallback((msg: Message) => {
    setMessages((prev) => {
      if (msg.event_type === "human_input_response") {
        const lastMsg = prev[prev.length - 1];
        if (lastMsg && lastMsg.role === "user" && lastMsg.content === msg.content) {
          return prev;
        }
      }
      return [...prev, msg];
    });
  }, []);

  const connectAndRun = useCallback(async (
    convId: string,
    payload: { prompt?: string; run_id?: string; after_sequence?: number }
  ) => {
    const userMsg: Message = {
      id: crypto.randomUUID(),
      conversation_id: convId,
      role: "user",
      content: payload.prompt ?? "",
      created_at: new Date().toISOString(),
    };

    if (payload.prompt) {
      addMessageLocal(userMsg);
    }

    setRunning(true);
    setActiveNodeId(null);

    const ws = new WebSocket(`${WS_BASE}/ws/conversations/${convId}/run`);
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify(payload));
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

      if (event.run_id) {
        activeRunIdRef.current = event.run_id;
      }

      if (event.type === "run_queued") {
        activeRunIdRef.current = event.run_id;
        return;
      }

      if (typeof event.sequence === "number") {
        if (event.sequence <= lastSequenceRef.current) {
          return;
        }
        lastSequenceRef.current = event.sequence;
      }

      if (
        event.type === "tool_approval_response" ||
        event.type === "human_input_response" ||
        event.type === "interrupt_response"
      ) {
        setActiveInterrupt((prev) => {
          const reqId = (event as any).request_id || (event as any).payload?.request_id;
          if (prev && (prev.request_id === reqId || !reqId)) {
            return null;
          }
            return prev;
        });
        const isToolApproval = event.type === "tool_approval_response" || (event as any).approved !== undefined;
        if (isToolApproval) {
          return;
        }
      }

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
        setActiveInterrupt(null);
        setActiveNodeId(null);
        resetLiveRunTracking();
        loadSidebar();
        refreshConversationName();
        return;
      }

      if (event.type === "run_aborted") {
        const abortedMessage = executionEventToMessage(event, {
          conversationId: convId,
          messageId: crypto.randomUUID(),
          createdAt: new Date().toISOString(),
        });
        if (abortedMessage) {
          addMessageLocal(abortedMessage);
        }
        setRunning(false);
        setActiveInterrupt(null);
        setActiveNodeId(null);
        resetLiveRunTracking();
        loadSidebar();
        return;
      }

      if (event.type === "error") {
        const errMsg = executionEventToMessage(event, {
          conversationId: convId,
          messageId: crypto.randomUUID(),
          createdAt: new Date().toISOString(),
        });
        if (errMsg) {
          addMessageLocal(errMsg);
        }
        setRunning(false);
        setActiveInterrupt(null);
        setActiveNodeId(null);
        resetLiveRunTracking();
        return;
      }

      let msgId = crypto.randomUUID();
      if (event.type === "human_input_request") {
        setActiveInterrupt({
          type: "human_input",
          request_id: event.request_id,
          message_id: msgId,
          question: event.question,
        });
      } else if (event.type === "tool_approval_request") {
        setActiveInterrupt({
          type: "tool_approval",
          request_id: event.request_id,
          message_id: msgId,
          tool: event.tool,
          args: event.args,
        });
      }

      const message = executionEventToMessage(event, {
        conversationId: convId,
        messageId: msgId,
        createdAt: new Date().toISOString(),
      });
      if (message) {
        addMessageLocal(message);
      }

      if ('node_id' in event && event.node_id) {
        setActiveNodeId(event.node_id as string);
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
      setActiveInterrupt(null);
      setActiveNodeId(null);
    };

    ws.onclose = (ev) => {
      if (wsRef.current === ws) wsRef.current = null;

      const isUnexpected = ev.code !== 1000 && ev.code !== 1005;

      if (isUnexpected && !manualStopRef.current && activeRunIdRef.current) {
        reconnectTimerRef.current = window.setTimeout(() => {
          connectAndRun(convId, {
            run_id: activeRunIdRef.current ?? undefined,
            after_sequence: lastSequenceRef.current,
          }).catch((err) => {
            console.error("Failed to reconnect websocket:", err);
          });
        }, 500);

        addMessageLocal({
          id: crypto.randomUUID(),
          conversation_id: convId,
          role: "system",
          content: "Connection interrupted. Attempting to reconnect...",
          event_type: "warning",
          created_at: new Date().toISOString(),
        });
        return;
      }

      if (isUnexpected) {
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
      setActiveInterrupt(null);
      setActiveNodeId(null);
      resetLiveRunTracking();
    };
  }, [conversation_id, loadSidebar, resetLiveRunTracking, setConversationName, setConversations, setActiveNodeId, addMessageLocal]);

  useEffect(() => {
    if (activeInterrupt?.type === "human_input") {
      setTimeout(() => {
        inlineInputRef.current?.focus();
      }, 50);
    }
  }, [activeInterrupt, inlineInputRef]);

  const handleSendHumanResponse = async (content: string) => {
    if (!activeInterrupt || !conversation_id) return;
    const runId = activeRunIdRef.current;
    if (runId) {
      try {
        await submitInterruptResponse(runId, activeInterrupt.request_id, "human_input_response", { content });
      } catch (err) {
        console.error("Failed to submit human input response:", err);
      }
    }
    const userMsg: Message = {
      id: crypto.randomUUID(),
      conversation_id,
      role: "user",
      content: content,
      event_type: "human_input_response",
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setActiveInterrupt(null);
    setTimeout(() => {
      chatInputRef.current?.focus();
    }, 50);
  };

  const handleSendToolApproval = async (approved: boolean) => {
    if (!activeInterrupt) return;
    const runId = activeRunIdRef.current;
    if (runId) {
      try {
        await submitInterruptResponse(runId, activeInterrupt.request_id, "tool_approval_response", { approved });
      } catch (err) {
        console.error("Failed to submit tool approval response:", err);
      }
    }
    setActiveInterrupt(null);
    setTimeout(() => {
      chatInputRef.current?.focus();
    }, 50);
  };

  useEffect(() => {
    setExpandedTurns(new Set());
    setCollapsedSteps(new Set());

    setRunning(false);
    setActiveInterrupt(null);
    setActiveNodeId(null);
    resetLiveRunTracking();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [conversation_id, resetLiveRunTracking, setActiveNodeId]);

  useEffect(() => {
    const checkAndReconnect = async () => {
      if (!conversation_id || conversation_id === "empty" || runningRef.current || loadingConv) return;

      try {
        const activeRun = await getActiveRun(conversation_id);
        if (
          activeRun &&
          (activeRun.status === "queued" ||
            activeRun.status === "running" ||
            activeRun.status === "aborting")
        ) {
          setActiveInterrupt(null);
          setMessages((prev) => {
            const runStartIdx = [...prev].reverse().findIndex(
              (m) => m.role === "user" && m.event_type !== "human_input_response"
            );
            if (runStartIdx !== -1) {
              const idx = prev.length - 1 - runStartIdx;
              return prev.slice(0, idx + 1);
            }
            return prev;
          });

          lastSequenceRef.current = 0;
          activeRunIdRef.current = activeRun.run_id;

          connectAndRun(conversation_id, {
            run_id: activeRun.run_id,
            after_sequence: 0,
          }).catch((err) => {
            console.error("Failed to reconnect active run on visibility change:", err);
          });
        }
      } catch (err) {
        console.error("Failed to check active run on tab visibility change:", err);
      }
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        checkAndReconnect();
      }
    };

    const handleFocus = () => {
      checkAndReconnect();
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("focus", handleFocus);

    checkAndReconnect();

    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("focus", handleFocus);
    };
  }, [conversation_id, loadingConv, connectAndRun]);

  const stopRun = async () => {
    manualStopRef.current = true;
    if (reconnectTimerRef.current !== null) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }

    let runId = activeRunIdRef.current;
    if (!runId && conversation_id && conversation_id !== "empty") {
      try {
        const activeRun = await getActiveRun(conversation_id);
        runId = activeRun?.run_id ?? null;
      } catch (err) {
        console.error("Failed to fetch active run before abort:", err);
      }
    }

    if (runId) {
      try {
        await abortRun(runId);
      } catch (err) {
        console.error("Failed to abort run:", err);
      }
    }

    wsRef.current?.close();
    setRunning(false);
    setActiveInterrupt(null);
    setActiveNodeId(null);
    resetLiveRunTracking();
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

  const toggleStepExpand = useCallback((stepId: string) => {
    setCollapsedSteps((prev) => {
      const next = new Set(prev);
      if (next.has(stepId)) {
        next.delete(stepId);
      } else {
        next.add(stepId);
      }
      return next;
    });
  }, []);

  return {
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
  };
}
