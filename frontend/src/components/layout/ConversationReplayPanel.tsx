import { useEffect, useMemo, useRef, useState } from "react";
import { Upload, ChevronLeft, ChevronRight, X, AlertCircle, GitCommitHorizontal, List } from "lucide-react";
import { getConversation, importConversationZip, listConversations } from "@/lib/api";
import { useCanvasStore } from "@/store/canvasStore";
import type { ConversationSummary, Message } from "@/types";
import type { Node } from "@xyflow/react";

function isToolResultMessage(message: Message | null): boolean {
  if (!message) {
    return false;
  }
  return message.event_type === "tool_result" || message.role === "tool";
}

function isReplayMessage(message: Message): boolean {
  return message.role === "user" || message.role === "assistant" || message.role === "tool";
}

function formatRole(message: Message): string {
  if (isToolResultMessage(message) && message.event_type !== "response") {
    return "Tool";
  }

  const role = message.role;
  if (role === "assistant") {
    return "Assistant";
  }
  if (role === "tool") {
    return "Tool";
  }
  return "User";
}

function getActorLabel(message: Message | null): string | null {
  if (!message) {
    return null;
  }

  if (isToolResultMessage(message) && message.event_type !== "response") {
    return message.agent_name?.trim() || "Tool";
  }

  if (message.role === "assistant") {
    return message.agent_name?.trim() || "Assistant";
  }

  return "User";
}

function getNodeName(node: Node): string | null {
  const data = node.data as { name?: string } | undefined;
  return data?.name?.trim().toLowerCase() || null;
}

function extractToolNameFromContent(content: string): string | null {
  const match = content.match(/Execution error in ([A-Za-z_][A-Za-z0-9_]*)\s*:/i);
  return match?.[1]?.trim().toLowerCase() || null;
}

function resolveToolNodeId(message: Message, nodes: Node[]): string | null {
  const toolNameCandidates = [
    message.agent_name?.trim().toLowerCase() || null,
    extractToolNameFromContent(message.content),
  ].filter((value): value is string => Boolean(value));

  for (const candidate of toolNameCandidates) {
    const toolNameMatch = nodes.find((node) => node.type === "tool" && getNodeName(node) === candidate);
    if (toolNameMatch) {
      return toolNameMatch.id;
    }
  }

  return null;
}

function resolveReplayNodeId(message: Message | null, nodes: Node[]): string | null {
  if (!message) {
    return null;
  }

  const toolNodeIdFromName = isToolResultMessage(message) ? resolveToolNodeId(message, nodes) : null;

  if (message.node_id) {
    if (nodes.length === 0) {
      return toolNodeIdFromName || message.node_id;
    }

    const directMatch = nodes.find((node) => node.id === message.node_id);
    if (directMatch) {
      if (isToolResultMessage(message) && directMatch.type !== "tool" && toolNodeIdFromName) {
        return toolNodeIdFromName;
      }
      return message.node_id;
    }
  }

  if (toolNodeIdFromName) {
    return toolNodeIdFromName;
  }

  const actorName = message.agent_name?.trim().toLowerCase();
  if (!actorName) {
    return null;
  }

  const nameMatch = nodes.find((node) => getNodeName(node) === actorName);
  return nameMatch?.id || null;
}

type ReplaySemanticType = "router" | "worker" | "tool" | "user" | "unknown";

const BUILTIN_TOOL_NAMES = new Set(["generate_plot", "run_code", "pip_install"]);

function isBuiltinToolActor(message: Message): boolean {
  const actorName = message.agent_name?.trim().toLowerCase();
  return Boolean(actorName && BUILTIN_TOOL_NAMES.has(actorName));
}

function resolveReplaySemanticType(message: Message, nodes: Node[]): ReplaySemanticType {
  if (isToolResultMessage(message)) {
    return "tool";
  }

  const resolvedNodeId = resolveReplayNodeId(message, nodes);
  if (resolvedNodeId) {
    const matchedNode = nodes.find((node) => node.id === resolvedNodeId);
    if (matchedNode?.type === "tool") {
      return "tool";
    }

    if (matchedNode?.type === "agent") {
      const agentData = matchedNode.data as { agentType?: string } | undefined;
      return agentData?.agentType === "router" ? "router" : "worker";
    }
  }

  if (isBuiltinToolActor(message)) {
    return "tool";
  }

  if (message.role === "assistant") {
    return "worker";
  }

  if (message.role === "user") {
    return "user";
  }

  return "unknown";
}

function getReplayBadgeColorClass(type: ReplaySemanticType): string {
  if (type === "router") {
    return "bg-[var(--color-agent-subtle)] text-[var(--color-agent)]";
  }
  if (type === "worker") {
    return "bg-[var(--color-accent-subtle)] text-[var(--color-accent)]";
  }
  if (type === "tool") {
    return "bg-[var(--color-secondary-subtle)] text-[var(--color-secondary)]";
  }
  if (type === "user") {
    return "bg-[var(--color-warning-subtle)] text-[var(--color-warning)]";
  }
  return "bg-[var(--color-border-subtle)] text-[var(--color-text-secondary)]";
}

function getReplayTickColorClass(type: ReplaySemanticType): string {
  if (type === "router") {
    return "bg-[var(--color-agent)]";
  }
  if (type === "worker") {
    return "bg-[var(--color-accent)]";
  }
  if (type === "tool") {
    return "bg-[var(--color-secondary)]";
  }
  if (type === "user") {
    return "bg-[var(--color-warning)]";
  }
  return "bg-[var(--color-border-strong)]";
}

const BASE_REPLAY_INTERVAL_MS = 1200;

export function ConversationReplayPanel() {
  const canvasId = useCanvasStore((s) => s.canvasId);
  const nodes = useCanvasStore((s) => s.nodes);
  const setActiveNodeId = useCanvasStore((s) => s.setActiveNodeId);

  const [messages, setMessages] = useState<Message[]>([]);
  const [conversationName, setConversationName] = useState<string>("");
  const [index, setIndex] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<boolean>(false);
  const [conversationList, setConversationList] = useState<ConversationSummary[]>([]);
  const [showConversationList, setShowConversationList] = useState<boolean>(false);
  const [conversationSearch, setConversationSearch] = useState<string>("");
  const [conversationSort, setConversationSort] = useState<"updated_desc" | "name_asc">("updated_desc");
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const replayMessages = useMemo(() => messages.filter(isReplayMessage), [messages]);
  const currentMessage = replayMessages[index] ?? null;
  const currentActor = getActorLabel(currentMessage);
  const currentSemanticType = useMemo(
    () => (currentMessage ? resolveReplaySemanticType(currentMessage, nodes) : "unknown"),
    [currentMessage, nodes]
  );
  const filteredSortedConversations = useMemo(() => {
    const searchValue = conversationSearch.trim().toLowerCase();
    const filtered = conversationList.filter((conversation) => {
      if (!searchValue) {
        return true;
      }
      return conversation.name.toLowerCase().includes(searchValue);
    });

    const sorted = [...filtered];
    if (conversationSort === "name_asc") {
      sorted.sort((a, b) => a.name.localeCompare(b.name));
      return sorted;
    }

    sorted.sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
    return sorted;
  }, [conversationList, conversationSearch, conversationSort]);
  const activeReplayNodeId = useMemo(
    () => resolveReplayNodeId(currentMessage, nodes),
    [currentMessage, nodes]
  );

  useEffect(() => {
    if (!activeReplayNodeId) {
      setActiveNodeId(null);
      return;
    }
    setActiveNodeId(activeReplayNodeId);
  }, [activeReplayNodeId, setActiveNodeId]);

  useEffect(() => {
    return () => {
      setActiveNodeId(null);
    };
  }, [setActiveNodeId]);

  useEffect(() => {
    if (!isPlaying || replayMessages.length === 0) {
      return;
    }

    const intervalMs = Math.max(250, Math.round(BASE_REPLAY_INTERVAL_MS / playbackSpeed));
    const timer = window.setInterval(() => {
      setIndex((prev) => Math.min(prev + 1, replayMessages.length - 1));
    }, intervalMs);

    return () => {
      window.clearInterval(timer);
    };
  }, [isPlaying, playbackSpeed, replayMessages.length]);

  useEffect(() => {
    if (!isPlaying) {
      return;
    }
    if (replayMessages.length === 0 || index >= replayMessages.length - 1) {
      setIsPlaying(false);
    }
  }, [index, isPlaying, replayMessages.length]);

  useEffect(() => {
    if (!expanded) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const tagName = target?.tagName?.toLowerCase() ?? "";
      const inputType = tagName === "input" ? (target as HTMLInputElement).type : null;
      const isTypingTarget =
        (tagName === "input" && inputType !== "range") ||
        tagName === "textarea" ||
        tagName === "select" ||
        target?.isContentEditable;

      if (isTypingTarget || replayMessages.length === 0) {
        return;
      }

      if (event.key === "ArrowLeft") {
        event.preventDefault();
        setIsPlaying(false);
        setIndex((prev) => Math.max(prev - 1, 0));
        return;
      }

      if (event.key === "ArrowRight") {
        event.preventDefault();
        setIsPlaying(false);
        setIndex((prev) => Math.min(prev + 1, replayMessages.length - 1));
        return;
      }

      if (event.key === "Home") {
        event.preventDefault();
        setIsPlaying(false);
        setIndex(0);
        return;
      }

      if (event.key === "End") {
        event.preventDefault();
        setIsPlaying(false);
        setIndex(replayMessages.length - 1);
        return;
      }

      if (event.key === " ") {
        event.preventDefault();
        setIsPlaying((prev) => {
          if (prev) {
            return false;
          }
          if (index >= replayMessages.length - 1) {
            setIndex(0);
          }
          return true;
        });
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [expanded, index, replayMessages.length]);

  const handleImportClick = () => {
    fileInputRef.current?.click();
  };

  const loadReplayConversation = (name: string, replayMessages: Message[]) => {
    setConversationName(name);
    setMessages(replayMessages);
    setIndex(0);
    setIsPlaying(false);
    setError(null);
  };

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || !canvasId) {
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const conversation = await importConversationZip(canvasId, file);
      loadReplayConversation(conversation.name, conversation.messages ?? []);
      setShowConversationList(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to import conversation";
      setError(message);
      setMessages([]);
      setConversationName("");
      setIndex(0);
      setIsPlaying(false);
      setActiveNodeId(null);
    } finally {
      setLoading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleBrowseConversations = async () => {
    if (!canvasId) {
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const conversations = await listConversations(canvasId);
      setConversationList(conversations);
      setConversationSearch("");
      setConversationSort("updated_desc");
      setShowConversationList(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load conversations";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectConversation = async (conversationId: string) => {
    if (!canvasId) {
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const conversation = await getConversation(canvasId, conversationId);
      loadReplayConversation(conversation.name, conversation.messages ?? []);
      setShowConversationList(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load conversation";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const stepBack = () => {
    setIsPlaying(false);
    setIndex((prev) => Math.max(prev - 1, 0));
  };

  const stepForward = () => {
    setIsPlaying(false);
    setIndex((prev) => Math.min(prev + 1, Math.max(replayMessages.length - 1, 0)));
  };

  const togglePlay = () => {
    if (replayMessages.length === 0 || loading) {
      return;
    }

    if (isPlaying) {
      setIsPlaying(false);
      return;
    }

    if (index >= replayMessages.length - 1) {
      setIndex(0);
    }
    setIsPlaying(true);
  };

  const handleTimelineChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setIsPlaying(false);
    setIndex(Number(event.target.value));
  };

  const handleTimelineKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (replayMessages.length === 0) {
      return;
    }

    if (event.key === "Home") {
      event.preventDefault();
      setIsPlaying(false);
      setIndex(0);
      return;
    }

    if (event.key === "End") {
      event.preventDefault();
      setIsPlaying(false);
      setIndex(replayMessages.length - 1);
    }
  };

  const handlePlaybackSpeedChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const speed = Number(event.target.value);
    setPlaybackSpeed(speed);
  };

  const clearReplay = () => {
    setMessages([]);
    setConversationName("");
    setIndex(0);
    setIsPlaying(false);
    setError(null);
    setShowConversationList(false);
    setConversationSearch("");
    setConversationSort("updated_desc");
    setActiveNodeId(null);
  };

  const timelineMax = Math.max(replayMessages.length - 1, 0);

  const getTickColorClass = (message: Message): string => getReplayTickColorClass(resolveReplaySemanticType(message, nodes));

  const formatUpdatedAt = (updatedAt: string): string => {
    const date = new Date(updatedAt);
    if (Number.isNaN(date.getTime())) {
      return "Updated unknown";
    }
    return `Updated ${date.toLocaleDateString()}`;
  };

  if (!canvasId) {
    return null;
  }

  if (!expanded) {
    return (
      <button
        type="button"
        onClick={() => setExpanded(true)}
        data-testid="replay-launcher-button"
        className="absolute right-4 top-14 z-30 w-11 h-11 rounded-full border border-[var(--color-border-default)] chrome-glass shadow-[0_8px_24px_rgba(0,0,0,0.3)] flex items-center justify-center text-[var(--color-text-primary)] hover:bg-[var(--color-elevated)] transition-all"
        title="Open conversation replay"
      >
        <GitCommitHorizontal className="w-4.5 h-4.5 text-[var(--color-accent)]" />
      </button>
    );
  }

  return (
    <div
      data-testid="conversation-replay-panel"
      className="absolute right-4 top-14 w-[340px] max-w-[calc(100vw-88px)] z-30 rounded-xl border border-[var(--color-border-default)] chrome-glass shadow-[0_8px_24px_rgba(0,0,0,0.3)]"
    >
      <div className="flex items-center justify-between px-3 py-2 border-b border-[var(--color-border-subtle)]">
        <div className="flex items-center gap-2 text-[12px] font-semibold text-[var(--color-text-primary)]">
          <GitCommitHorizontal className="w-4 h-4 text-[var(--color-accent)]" />
          Conversation Replay
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={clearReplay}
            disabled={loading || replayMessages.length === 0}
            className="p-1 rounded text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-elevated)] disabled:opacity-40"
            title="Clear replay"
            data-testid="replay-clear-button"
          >
            <X className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => setExpanded(false)}
            className="p-1 rounded text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-elevated)]"
            title="Collapse replay"
            data-testid="replay-collapse-button"
          >
            <GitCommitHorizontal className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <div className="px-3 py-3 space-y-3">
        <div className="flex items-center gap-2">
          <button
            onClick={handleBrowseConversations}
            disabled={loading}
            className="btn-secondary text-[11px] px-2.5 py-1.5 flex items-center gap-1.5 disabled:opacity-60"
            data-testid="replay-browse-button"
          >
            <List className="w-3.5 h-3.5" />
            Browse
          </button>
          <button
            onClick={handleImportClick}
            disabled={loading}
            className="btn-secondary text-[11px] px-2.5 py-1.5 flex items-center gap-1.5 disabled:opacity-60"
            data-testid="replay-import-button"
          >
            <Upload className="w-3.5 h-3.5" />
            {loading ? "Importing..." : "Import"}
          </button>
          {conversationName && (
            <span className="text-[11px] text-[var(--color-text-secondary)] truncate" data-testid="replay-conversation-name">
              {conversationName}
            </span>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept=".zip"
            className="hidden"
            onChange={handleFileChange}
            data-testid="replay-file-input"
          />
        </div>

        {error && (
          <div
            className="rounded-md border border-[var(--color-danger)]/30 bg-[var(--color-danger-subtle)] text-[11px] text-[var(--color-danger)] px-2.5 py-2 flex items-start gap-2"
            data-testid="replay-error"
          >
            <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {showConversationList && (
          <div
            className="rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-surface)] p-1.5 max-h-40 overflow-y-auto"
            data-testid="replay-conversation-list"
          >
            <div className="mb-1.5 px-0.5 flex items-center gap-1.5">
              <input
                type="text"
                value={conversationSearch}
                onChange={(event) => setConversationSearch(event.target.value)}
                placeholder="Search"
                className="flex-1 min-w-0 text-[11px] rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-inset)] text-[var(--color-text-primary)] px-2 py-1"
                data-testid="replay-conversation-search"
              />
              <select
                value={conversationSort}
                onChange={(event) => setConversationSort(event.target.value as "updated_desc" | "name_asc")}
                className="text-[11px] rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-inset)] text-[var(--color-text-primary)] px-1.5 py-1"
                data-testid="replay-conversation-sort"
              >
                <option value="updated_desc">Recent</option>
                <option value="name_asc">Name</option>
              </select>
            </div>
            {filteredSortedConversations.length > 0 ? (
              filteredSortedConversations.map((conversation) => (
                <button
                  key={conversation.id}
                  type="button"
                  onClick={() => handleSelectConversation(conversation.id)}
                  aria-label={conversation.name}
                  className="w-full text-left px-2.5 py-2 rounded-md hover:bg-[var(--color-elevated)] transition-colors"
                >
                  <span className="block text-[11px] text-[var(--color-text-primary)] truncate" data-testid="replay-conversation-item-name">
                    {conversation.name}
                  </span>
                  <div className="mt-1 flex items-center gap-1.5">
                    <span
                      className="inline-flex items-center rounded-full px-1.5 py-0.5 text-[9px] uppercase tracking-wide bg-[var(--color-elevated)] text-[var(--color-text-secondary)]"
                      data-testid={`replay-conversation-item-status-${conversation.id}`}
                      aria-hidden="true"
                    >
                      {conversation.status}
                    </span>
                    <span
                      className="text-[9px] text-[var(--color-text-tertiary)]"
                      data-testid={`replay-conversation-item-updated-${conversation.id}`}
                      aria-hidden="true"
                    >
                      {formatUpdatedAt(conversation.updated_at)}
                    </span>
                  </div>
                </button>
              ))
            ) : (
              <div className="px-2.5 py-2 text-[11px] text-[var(--color-text-tertiary)]">
                No matching conversations for this canvas.
              </div>
            )}
          </div>
        )}

        <div className="rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-surface)] p-2.5 h-[170px] flex flex-col">
          {currentMessage ? (
            <>
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-1.5 min-w-0">
                  <span
                    className={`text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded-md font-semibold ${getReplayBadgeColorClass(currentSemanticType)}`}
                    data-testid="replay-current-role"
                  >
                    {formatRole(currentMessage)}
                  </span>
                  {currentActor && (
                    <span
                      className="text-[10px] text-[var(--color-text-secondary)] truncate"
                      data-testid="replay-current-actor"
                    >
                      {currentActor}
                    </span>
                  )}
                </div>
                <span className="text-[10px] text-[var(--color-text-tertiary)]" data-testid="replay-step-indicator">
                  {index + 1}/{replayMessages.length}
                </span>
              </div>
              <div className="flex-1 min-h-0 overflow-y-auto text-[12px] text-[var(--color-text-primary)] whitespace-pre-wrap leading-relaxed pr-1" data-testid="replay-current-message">
                {currentMessage.content}
              </div>
            </>
          ) : (
            <div className="flex-1 min-h-0 flex items-center justify-center text-center text-[11px] text-[var(--color-text-tertiary)]">
              Import a conversation ZIP to replay user and assistant messages on the canvas.
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={togglePlay}
            disabled={loading || replayMessages.length === 0}
            className="btn-secondary text-[11px] px-2.5 py-1.5 disabled:opacity-50"
            data-testid="replay-play-button"
          >
            {isPlaying ? "Pause" : "Play"}
          </button>
          <select
            value={String(playbackSpeed)}
            onChange={handlePlaybackSpeedChange}
            disabled={loading || replayMessages.length === 0}
            className="text-[11px] rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-surface)] text-[var(--color-text-primary)] px-2 py-1.5 disabled:opacity-50"
            aria-label="Replay speed"
            data-testid="replay-speed-select"
          >
            <option value="0.5">0.5x</option>
            <option value="1">1x</option>
            <option value="2">2x</option>
          </select>
          <button
            onClick={stepBack}
            disabled={loading || replayMessages.length === 0 || index === 0}
            className="btn-secondary text-[11px] px-2.5 py-1.5 flex items-center gap-1 disabled:opacity-50"
            data-testid="replay-prev-button"
          >
            <ChevronLeft className="w-3.5 h-3.5" />
            Previous
          </button>
          <button
            onClick={stepForward}
            disabled={loading || replayMessages.length === 0 || index >= replayMessages.length - 1}
            className="btn-secondary text-[11px] px-2.5 py-1.5 flex items-center gap-1 disabled:opacity-50"
            data-testid="replay-next-button"
          >
            Next
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>

        <input
          type="range"
          min={0}
          max={timelineMax}
          step={1}
          value={Math.min(index, timelineMax)}
          onChange={handleTimelineChange}
          onKeyDown={handleTimelineKeyDown}
          disabled={loading || replayMessages.length === 0}
          className="w-full accent-[var(--color-accent)] disabled:opacity-50"
          aria-label="Replay timeline"
          data-testid="replay-timeline-slider"
        />

        <div className="w-full flex items-center gap-1" data-testid="replay-timeline-rail">
          {replayMessages.map((message, stepIndex) => {
            const isActive = stepIndex === index;
            return (
              <button
                key={message.id}
                type="button"
                onClick={() => {
                  setIsPlaying(false);
                  setIndex(stepIndex);
                }}
                className={`h-2 flex-1 rounded-full transition-all ${getTickColorClass(message)} ${
                  isActive ? "ring-1 ring-[var(--color-text-primary)]" : "opacity-55 hover:opacity-90"
                }`}
                aria-label={`Jump to step ${stepIndex + 1}`}
                data-testid={`replay-timeline-tick-${stepIndex}`}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}
