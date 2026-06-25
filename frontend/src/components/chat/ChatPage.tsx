import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { useParams, useNavigate, Link, useSearchParams, useLocation } from "react-router-dom";
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
  Download,
  Upload,
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
  apiOrigin,
  exportConversationZip,
  importConversationZip,
  listCanvases,
  getActiveRun,
  abortRun,
  submitInterruptResponse,
} from "@/lib/api";
import type { ConversationSummary, Message, ExecutionEvent, CanvasResponse, CanvasListItem } from "@/types";
import { executionEventToMessage } from "./executionEventMessage";

const WS_BASE = `ws://${import.meta.env.VITE_API_HOST || "localhost:8000"}`;


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
        if (currentTurn.humanInterrupt?.event_type === "tool_approval_request") {
          currentTurn.isStreaming = true;
        }
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

  // Build adjacency list: node_id -> list of target node_ids
  const adj: Record<string, string[]> = {};
  // Track incoming edges of any type
  const hasIncoming = new Set<string>();

  for (const edge of edges) {
    if (!adj[edge.source_node_id]) {
      adj[edge.source_node_id] = [];
    }
    adj[edge.source_node_id].push(edge.target_node_id);
    hasIncoming.add(edge.target_node_id);
  }

  // Find root nodes: agents with no incoming edges
  const roots = agents.filter(a => !hasIncoming.has(a.id));

  // If no roots (e.g. cycle or empty), use all agents as fallback roots
  const initialNodes = roots.length > 0 ? roots : agents;

  // BFS queue: { id, level }
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

  // Handle any nodes that were not reached by the BFS (e.g., disconnected subgraphs)
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

  const setActiveNodeId = useCanvasStore((s) => s.setActiveNodeId);
  const theme = useThemeStore((s) => s.theme);
  const sidebarCollapsed = useCanvasStore((s) => s.sidebarCollapsed);
  const setSidebarCollapsed = useCanvasStore((s) => s.setSidebarCollapsed);

  const [canvasId, setCanvasId] = useState<string | null>(null);
  const [canvasName, setCanvasName] = useState<string>("Canvas");
  const [canvas, setCanvas] = useState<CanvasResponse | null>(null);
  const [conversationName, setConversationName] = useState<string>("Chat");
  const [allCanvases, setAllCanvases] = useState<CanvasListItem[]>([]);

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
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [loadingConv, setLoadingConv] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedTurns, setExpandedTurns] = useState<Set<string>>(() => new Set());
  const [collapsedSteps, setCollapsedSteps] = useState<Set<string>>(() => new Set());
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [activeInterrupt, setActiveInterrupt] = useState<{
    type: "human_input" | "tool_approval";
    request_id: string;
    message_id: string;
    question?: string;
    tool?: string;
    args?: Record<string, unknown>;
  } | null>(null);

  const chatInputRef = useRef<HTMLInputElement>(null);
  const inlineInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (activeInterrupt?.type === "human_input") {
      setTimeout(() => {
        inlineInputRef.current?.focus();
      }, 50);
    }
  }, [activeInterrupt]);

  const handleSendHumanResponse = async (content: string) => {
    if (!activeInterrupt) return;
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
      conversation_id: conversation_id!,
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

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
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

  const localMessagesRef = useRef<Message[]>([]);

  useEffect(() => {
    localMessagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Reset states and clean up active websocket when switching conversations
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
  }, [conversation_id, resetLiveRunTracking]);

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

        // Fetch canvas name
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
  }, [conversation_id, queryCanvasId, allCanvases, navigate]);

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

  const addMessageLocal = (msg: Message) => {
    setMessages((prev) => [...prev, msg]);
  };



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
          if (prev && prev.request_id === event.request_id) {
            return null;
          }
          return prev;
        });
        return;
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
        loadSidebar(); // Refresh sidebar order since conversation updated
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

      if (event.node_id) {
        setActiveNodeId(event.node_id);
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
  }, [conversation_id, loadSidebar, resetLiveRunTracking]);

  const handleSend = () => {
    if (!input.trim() || !conversation_id || running) return;

    const prompt = input.trim();
    setInput("");

    resetLiveRunTracking();
    connectAndRun(conversation_id, { prompt });
  };

  // Check active runs and reconnect on tab visibility/focus changes
  useEffect(() => {
    const checkAndReconnect = async () => {
      if (!conversation_id || conversation_id === "empty" || running || loadingConv) return;

      try {
        const activeRun = await getActiveRun(conversation_id);
        if (
          activeRun &&
          (activeRun.status === "queued" ||
            activeRun.status === "running" ||
            activeRun.status === "aborting")
        ) {
          // Clean up any replayed steps of the active run from the message history
          // to prevent duplicate items during replay.
          setMessages((prev) => {
            const lastUserIdx = [...prev].reverse().findIndex((m) => m.role === "user");
            if (lastUserIdx !== -1) {
              const idx = prev.length - 1 - lastUserIdx;
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

    // Initial check on mount/load
    checkAndReconnect();

    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("focus", handleFocus);
    };
  }, [conversation_id, running, loadingConv, connectAndRun]);



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

  const navItemClass = (toPath: string) => {
    const isExact = location.pathname.startsWith(toPath);
    const isHome = toPath === "/";
    const isActive = isHome ? location.pathname === "/" : isExact;
    
    return sidebarCollapsed
      ? `flex items-center justify-center w-10 h-10 mx-auto rounded-lg transition-all ${
          isActive
            ? "bg-[var(--color-elevated)] text-[var(--color-text-primary)] border border-[var(--color-border-default)]"
            : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-elevated)] border border-transparent"
        }`
      : `w-full flex items-center gap-2.5 px-3 h-10 rounded-lg text-xs font-medium transition-all whitespace-nowrap ${
          isActive
            ? "bg-[var(--color-elevated)] text-[var(--color-text-primary)] border border-[var(--color-border-default)]"
            : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-elevated)] border border-transparent"
        }`;
  };

  const { preTurnMessages, turns } = groupMessagesIntoTurns(messages);

  const isEmpty = !conversation_id || conversation_id === "empty";

  return (
    <div className="h-screen w-screen flex bg-[var(--color-base)] noise-bg relative overflow-hidden">
      {/* Left Sidebar Panel */}
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
                              const isResponse = stepMsg.event_type === "response";

                              const level = getMessageNestingLevel(stepMsg);
                              const isStepCollapsed = collapsedSteps.has(stepMsg.id);
                              return (
                                <div
                                  key={stepMsg.id}
                                  className="flex flex-col items-start w-full"
                                  style={{
                                    animation: "staggerFadeIn 0.3s ease-out",
                                    paddingLeft: `${level * 24}px`,
                                    transition: "padding-left 0.2s ease-out",
                                  }}
                                >
                                  <button
                                    onClick={() => toggleStepExpand(stepMsg.id)}
                                    className="flex items-center gap-1.5 text-[10px] text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)] transition-colors cursor-pointer px-1 font-semibold tracking-wide mb-0.5"
                                  >
                                    {isStepCollapsed ? (
                                      <ChevronRight className="w-3 h-3" />
                                    ) : (
                                      <ChevronDown className="w-3 h-3" />
                                    )}
                                    <span>
                                      {stepMsg.agent_name || (isError || isWarning || isHandoff ? "System" : "Agent")}
                                      {stepMsg.event_type &&
                                        stepMsg.event_type !== "final_answer" &&
                                        ` · ${stepMsg.event_type}`}
                                    </span>
                                  </button>

                                  {!isStepCollapsed && (
                                    <div
                                      className={`max-w-[85%] w-full rounded-xl px-3 py-2 text-[12px] leading-relaxed shadow-sm ${isHandoff
                                        ? "bg-[var(--color-info-subtle)] text-[var(--color-info)] border border-[var(--color-info)]/20 rounded-bl-sm"
                                        : isError
                                          ? "bg-[var(--color-danger-subtle)] text-[var(--color-danger)] border border-[var(--color-danger)]/20 rounded-bl-sm"
                                          : isWarning || stepMsg.event_type === "tool_approval_request"
                                            ? "bg-[var(--color-warning-subtle)] text-[var(--color-warning)] border border-[var(--color-warning)]/20 rounded-bl-sm"
                                            : isThought
                                              ? "bg-[var(--color-agent-subtle)] text-[var(--color-agent)] border border-[var(--color-agent)]/20 rounded-bl-sm font-mono whitespace-pre-wrap text-[11px]"
                                              : stepMsg.event_type === "human_input_request"
                                                ? "bg-[var(--color-agent-subtle)] text-[var(--color-agent)] border border-[var(--color-agent)]/20 rounded-bl-sm"
                                                : isToolResult
                                                  ? "bg-[var(--color-success-subtle)] text-[var(--color-success)] border border-[var(--color-success)]/20 rounded-bl-sm font-mono"
                                                  : isResponse
                                                    ? "bg-[var(--color-agent-subtle)] text-[var(--color-agent)] border border-[var(--color-agent)]/20 rounded-bl-sm"
                                                    : isSubAnswer
                                                      ? "bg-[var(--color-elevated)] text-[var(--color-text-secondary)] border border-[var(--color-border-subtle)] rounded-bl-sm"
                                                      : "bg-[var(--color-elevated)] text-[var(--color-text-primary)] border border-[var(--color-border-subtle)] rounded-bl-sm"
                                        }`}
                                    >
                                      {stepMsg.event_type === "human_input_request" && stepMsg.id === activeInterrupt?.message_id ? (
                                        <div className="space-y-3 w-full">
                                          <div className="text-[var(--color-text-primary)] font-medium">
                                            {stepMsg.content}
                                          </div>
                                          <form
                                            onSubmit={(e) => {
                                              e.preventDefault();
                                              const form = e.currentTarget;
                                              const data = new FormData(form);
                                              const val = (data.get("response") as string || "").trim();
                                              if (!val) return;
                                              handleSendHumanResponse(val);
                                            }}
                                            className="flex gap-2 w-full mt-1.5"
                                          >
                                            <input
                                              ref={inlineInputRef}
                                              name="response"
                                              type="text"
                                              required
                                              placeholder="Type your response..."
                                              className="input-base flex-1 py-1.5 px-3 rounded-lg text-[12px] bg-[var(--color-base)] text-[var(--color-text-primary)] border border-[var(--color-border-default)] focus:border-[var(--color-accent)]"
                                            />
                                            <button
                                              type="submit"
                                              className="px-3.5 py-1.5 bg-[var(--color-accent)] hover:bg-[var(--color-accent-bright)] text-white text-[11px] font-semibold rounded-lg shadow transition-colors"
                                            >
                                              Submit
                                            </button>
                                          </form>
                                        </div>
                                      ) : stepMsg.event_type === "tool_approval_request" && stepMsg.id === activeInterrupt?.message_id ? (
                                        <div className="space-y-2.5 w-full">
                                          <div className="text-[var(--color-text-primary)] font-medium flex items-center gap-1.5">
                                            <span className="w-2 h-2 rounded-full bg-[var(--color-warning)] animate-ping" />
                                            <span>Tool Approval Required</span>
                                          </div>
                                          <div className="bg-[var(--color-base)] border border-[var(--color-border-subtle)] rounded-lg p-2.5 font-mono text-[11px] text-[var(--color-text-secondary)] space-y-1 max-w-full overflow-x-auto">
                                            <div><strong>Tool:</strong> {activeInterrupt.tool}</div>
                                            {activeInterrupt.args && Object.keys(activeInterrupt.args).length > 0 && (
                                              <div>
                                                <strong>Arguments:</strong>
                                                <pre className="mt-1 p-1.5 bg-[var(--color-elevated)] rounded border border-[var(--color-border-subtle)]/50 text-[10px] overflow-x-auto whitespace-pre-wrap">
                                                  {JSON.stringify(activeInterrupt.args, null, 2)}
                                                </pre>
                                              </div>
                                            )}
                                          </div>
                                          <div className="flex gap-2 mt-1">
                                            <button
                                              onClick={() => handleSendToolApproval(true)}
                                              className="px-3.5 py-1.5 bg-[var(--color-success)] hover:bg-[var(--color-success)]/90 text-white text-[11px] font-semibold rounded-lg shadow flex items-center gap-1 transition-colors"
                                            >
                                              Approve
                                            </button>
                                            <button
                                              onClick={() => handleSendToolApproval(false)}
                                              className="px-3.5 py-1.5 bg-[var(--color-danger)] hover:bg-[var(--color-danger)]/90 text-white text-[11px] font-semibold rounded-lg shadow flex items-center gap-1 transition-colors"
                                            >
                                              Deny
                                            </button>
                                          </div>
                                        </div>
                                      ) : (
                                        renderMessageContent(stepMsg.content, true)
                                      )}
                                    </div>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        )}

                        {/* Human Interrupt Request (visible outside only when collapsed) */}
                        {!isStreaming && !isExpanded && turn.humanInterrupt && (
                          <div
                            className="flex flex-col items-start w-full animate-fade-in"
                            style={{ animation: "staggerFadeIn 0.3s ease-out" }}
                          >
                            {turn.humanInterrupt.agent_name && (
                              <span className="text-[10px] text-[var(--color-text-tertiary)] mb-0.5 px-1 font-semibold tracking-wide">
                                {turn.humanInterrupt.agent_name} · {turn.humanInterrupt.event_type === "tool_approval_request" ? "tool_approval_request" : "human_input_request"}
                              </span>
                            )}
                            <div
                              className={`max-w-[85%] w-full rounded-xl px-3 py-2.5 text-[12px] leading-relaxed shadow-sm ${
                                turn.humanInterrupt.event_type === "tool_approval_request"
                                  ? "bg-[var(--color-warning-subtle)] text-[var(--color-warning)] border border-[var(--color-warning)]/20 rounded-bl-sm"
                                  : "bg-[var(--color-agent-subtle)] text-[var(--color-agent)] border border-[var(--color-agent)]/20 rounded-bl-sm"
                              }`}
                            >
                              {turn.humanInterrupt.event_type === "human_input_request" && turn.humanInterrupt.id === activeInterrupt?.message_id ? (
                                <div className="space-y-3 w-full">
                                  <div className="text-[var(--color-text-primary)] font-medium">
                                    {turn.humanInterrupt.content}
                                  </div>
                                  <form
                                    onSubmit={(e) => {
                                      e.preventDefault();
                                      const form = e.currentTarget;
                                      const data = new FormData(form);
                                      const val = (data.get("response") as string || "").trim();
                                      if (!val) return;
                                      handleSendHumanResponse(val);
                                    }}
                                    className="flex gap-2 w-full mt-1.5"
                                  >
                                    <input
                                      ref={inlineInputRef}
                                      name="response"
                                      type="text"
                                      required
                                      placeholder="Type your response..."
                                      className="input-base flex-1 py-1.5 px-3 rounded-lg text-[12px] bg-[var(--color-base)] text-[var(--color-text-primary)] border border-[var(--color-border-default)] focus:border-[var(--color-accent)]"
                                    />
                                    <button
                                      type="submit"
                                      className="px-3.5 py-1.5 bg-[var(--color-accent)] hover:bg-[var(--color-accent-bright)] text-white text-[11px] font-semibold rounded-lg shadow transition-colors"
                                    >
                                      Submit
                                    </button>
                                  </form>
                                </div>
                              ) : turn.humanInterrupt.event_type === "tool_approval_request" && turn.humanInterrupt.id === activeInterrupt?.message_id ? (
                                <div className="space-y-2.5 w-full">
                                  <div className="text-[var(--color-text-primary)] font-medium flex items-center gap-1.5">
                                    <span className="w-2 h-2 rounded-full bg-[var(--color-warning)] animate-ping" />
                                    <span>Tool Approval Required</span>
                                  </div>
                                  <div className="bg-[var(--color-base)] border border-[var(--color-border-subtle)] rounded-lg p-2.5 font-mono text-[11px] text-[var(--color-text-secondary)] space-y-1 max-w-full overflow-x-auto">
                                    <div><strong>Tool:</strong> {activeInterrupt.tool}</div>
                                    {activeInterrupt.args && Object.keys(activeInterrupt.args).length > 0 && (
                                      <div>
                                        <strong>Arguments:</strong>
                                        <pre className="mt-1 p-1.5 bg-[var(--color-elevated)] rounded border border-[var(--color-border-subtle)]/50 text-[10px] overflow-x-auto whitespace-pre-wrap">
                                          {JSON.stringify(activeInterrupt.args, null, 2)}
                                        </pre>
                                      </div>
                                    )}
                                  </div>
                                  <div className="flex gap-2 mt-1">
                                    <button
                                      onClick={() => handleSendToolApproval(true)}
                                      className="px-3.5 py-1.5 bg-[var(--color-success)] hover:bg-[var(--color-success)]/90 text-white text-[11px] font-semibold rounded-lg shadow flex items-center gap-1 transition-colors"
                                    >
                                      Approve
                                    </button>
                                    <button
                                      onClick={() => handleSendToolApproval(false)}
                                      className="px-3.5 py-1.5 bg-[var(--color-danger)] hover:bg-[var(--color-danger)]/90 text-white text-[11px] font-semibold rounded-lg shadow flex items-center gap-1 transition-colors"
                                    >
                                      Deny
                                    </button>
                                  </div>
                                </div>
                              ) : (
                                renderMessageContent(turn.humanInterrupt.content, true)
                              )}
                            </div>
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
                              {renderMessageContent(turn.finalAnswer.content)}
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
