import { useCanvasStore } from "@/store/canvasStore";
import { Wrench } from "lucide-react";

const MODEL_SUGGESTIONS = [
  "ollama:llama3.1",
  "ollama:llama3.2",
  "ollama:mistral",
  "ollama:codellama",
  "ollama:gemma4:31b",
  "openai:gpt-4o",
  "openai:gpt-4o-mini",
  "anthropic:claude-sonnet-4-20250514",
  "groq:llama-3.1-70b-versatile",
];
export function AgentEditor() {
  const selectedNodeId = useCanvasStore((s) => s.selectedNodeId);
  const nodes = useCanvasStore((s) => s.nodes);
  const setNodes = useCanvasStore((s) => s.setNodes);

  const selectedNode = nodes.find((n) => n.id === selectedNodeId && n.type === "agent");

  if (!selectedNode) {
    return (
      <div className="flex items-center justify-center h-full text-[var(--color-text-tertiary)] text-[12px]">
        Select an agent node to edit its properties
      </div>
    );
  }

  const data = selectedNode.data ?? {};

  const updateField = (field: string, value: string) => {
    const updatedNodes = nodes.map((n) =>
      n.id === selectedNodeId
        ? { ...n, data: { ...n.data, [field]: value } }
        : n
    );
    setNodes(updatedNodes);
  };

  const edges = useCanvasStore((s) => s.edges);
  const selectNode = useCanvasStore((s) => s.selectNode);

  const connectedTools = nodes.filter((n) => {
    if (n.type !== "tool") return false;
    return edges.some(edge => edge.source === selectedNodeId && edge.target === n.id);
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 pb-3 border-b border-[var(--color-border-subtle)]">
        <div className="w-5 h-5 rounded-md bg-[var(--color-accent-subtle)] flex items-center justify-center">
          <svg className="w-3 h-3 text-[var(--color-accent)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 2a4 4 0 0 1 4 4v1a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/>
            <path d="M12 12c-4 0-7 2-7 5v2h14v-2c0-3-3-5-7-5z"/>
          </svg>
        </div>
        <h3 className="text-[13px] font-semibold text-[var(--color-text-primary)]">Agent Properties</h3>
      </div>

      <div>
        <label className="block text-[11px] font-semibold text-[var(--color-text-tertiary)] mb-1.5 uppercase tracking-[0.06em]">Type</label>
        <select
          value={(data as any).agentType ?? "worker"}
          onChange={(e) => updateField("agentType", e.target.value)}
          data-testid="agent-type-select"
          className="input-base w-full"
        >
          <option value="worker">Worker</option>
          <option value="router">Router</option>
        </select>
      </div>

      <div>
        <label className="block text-[11px] font-semibold text-[var(--color-text-tertiary)] mb-1.5 uppercase tracking-[0.06em]">Name</label>
        <input
          type="text"
          value={(data as any).name ?? ""}
          onChange={(e) => updateField("name", e.target.value)}
          data-testid="agent-name-input"
          className="input-base w-full"
          placeholder="Agent name"
        />
      </div>

      <div>
        <label className="block text-[11px] font-semibold text-[var(--color-text-tertiary)] mb-1.5 uppercase tracking-[0.06em]">Role</label>
        <input
          type="text"
          value={(data as any).role ?? ""}
          onChange={(e) => updateField("role", e.target.value)}
          data-testid="agent-role-input"
          className="input-base w-full"
          placeholder="e.g. You are a helpful assistant"
        />
      </div>

      <div>
        <label className="block text-[11px] font-semibold text-[var(--color-text-tertiary)] mb-1.5 uppercase tracking-[0.06em]">Instructions</label>
        <textarea
          value={(data as any).instructions ?? ""}
          onChange={(e) => updateField("instructions", e.target.value)}
          data-testid="agent-instructions-input"
          rows={4}
          className="input-base w-full resize-none"
          placeholder="Instructions for the agent..."
        />
      </div>

      <div>
        <label className="block text-[11px] font-semibold text-[var(--color-text-tertiary)] mb-1.5 uppercase tracking-[0.06em]">Model</label>
        <input
          type="text"
          list="model-suggestions"
          value={(data as any).modelName ?? "ollama:llama3.1"}
          onChange={(e) => updateField("modelName", e.target.value)}
          data-testid="agent-model-input"
          className="input-base w-full"
          placeholder="e.g. ollama:gemma4:31b"
        />
        <datalist id="model-suggestions">
          {MODEL_SUGGESTIONS.map((m) => (
            <option key={m} value={m} />
          ))}
        </datalist>
      </div>

      <div className="pt-4 border-t border-[var(--color-border-subtle)] space-y-3">
        <h4 className="text-[11px] font-semibold text-[var(--color-text-tertiary)] uppercase tracking-[0.06em]">Capabilities</h4>

        <div>
          <label className="flex items-center gap-2.5 cursor-pointer group">
            <input
              type="checkbox"
              checked={(data as any).enableMemory ?? false}
              onChange={(e) => {
                const checked = e.target.checked;
                const updatedNodes = nodes.map((n) =>
                  n.id === selectedNodeId
                    ? { ...n, data: { ...n.data, enableMemory: checked } }
                    : n
                );
                setNodes(updatedNodes);
              }}
              data-testid="agent-enable-memory"
              className="rounded border-[var(--color-border-default)] text-[var(--color-accent)] focus:ring-[var(--color-accent)] bg-[var(--color-base)]"
            />
            <div>
              <span className="text-[12px] font-medium text-[var(--color-text-secondary)] group-hover:text-[var(--color-text-primary)] transition-colors">Enable Memory</span>
              <p className="text-[10px] text-[var(--color-text-tertiary)] mt-0.5">Agent stores and retrieves long-term memories</p>
            </div>
          </label>
        </div>

        {(data as any).agentType === "router" && (
          <div>
            <label className="flex items-center gap-2.5 cursor-pointer group">
              <input
                type="checkbox"
                checked={(data as any).enableConversationHistory ?? false}
                onChange={(e) => {
                  const checked = e.target.checked;
                  const updatedNodes = nodes.map((n) =>
                    n.id === selectedNodeId
                      ? { ...n, data: { ...n.data, enableConversationHistory: checked } }
                      : n
                  );
                  setNodes(updatedNodes);
                }}
                data-testid="agent-enable-history"
                className="rounded border-[var(--color-border-default)] text-[var(--color-accent)] focus:ring-[var(--color-accent)] bg-[var(--color-base)]"
              />
              <div>
                <span className="text-[12px] font-medium text-[var(--color-text-secondary)] group-hover:text-[var(--color-text-primary)] transition-colors">Enable Conversation History</span>
                <p className="text-[10px] text-[var(--color-text-tertiary)] mt-0.5">Agent sees prior conversation turns</p>
              </div>
            </label>
          </div>
        )}

        <div className="pt-3 border-t border-[var(--color-border-subtle)]">
          <h4 className="text-[11px] font-semibold text-[var(--color-text-tertiary)] mb-2 uppercase tracking-[0.06em] flex items-center gap-1.5">
            <Wrench className="w-3 h-3" /> Connected Tools
          </h4>
          <div className="space-y-1">
            {connectedTools.length > 0 ? (
              connectedTools.map((tool) => (
                <div
                  key={tool.id}
                  className="flex items-center justify-between px-2.5 py-1.5 bg-[var(--color-secondary-surface)] text-[var(--color-secondary)] border border-[var(--color-secondary)]/15 rounded-lg text-[11px] font-medium transition-colors hover:border-[var(--color-secondary)]/30"
                >
                  <span className="truncate">{tool.data.name}</span>
                  <button
                    onClick={() => selectNode(tool.id)}
                    className="text-[var(--color-secondary)] hover:text-[var(--color-secondary-bright)] font-bold px-1 transition-colors"
                  >
                    →
                  </button>
                </div>
              ))
            ) : (
              <p className="text-[11px] text-[var(--color-text-tertiary)] italic">No tools connected</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}