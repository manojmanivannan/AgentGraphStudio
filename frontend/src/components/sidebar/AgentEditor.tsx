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
      <div className="flex items-center justify-center h-full text-gray-400 text-sm">
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
      <h3 className="text-sm font-semibold text-gray-700 border-b pb-2">Agent Properties</h3>

      <div>
        <label className="block text-xs font-medium text-gray-500 mb-1">Type</label>
        <select
          value={(data as any).agentType ?? "worker"}
          onChange={(e) => updateField("agentType", e.target.value)}
          data-testid="agent-type-select"
          className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded-md focus:outline-none focus:ring-1 focus:ring-indigo-400 focus:border-indigo-400 bg-white"
        >
          <option value="worker">Worker</option>
          <option value="router">Router</option>
        </select>
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-500 mb-1">Name</label>
        <input
          type="text"
          value={(data as any).name ?? ""}
          onChange={(e) => updateField("name", e.target.value)}
          data-testid="agent-name-input"
          className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded-md focus:outline-none focus:ring-1 focus:ring-indigo-400 focus:border-indigo-400"
          placeholder="Agent name"
        />
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-500 mb-1">Role</label>
        <input
          type="text"
          value={(data as any).role ?? ""}
          onChange={(e) => updateField("role", e.target.value)}
          data-testid="agent-role-input"
          className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded-md focus:outline-none focus:ring-1 focus:ring-indigo-400 focus:border-indigo-400"
          placeholder="e.g. You are a helpful assistant"
        />
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-500 mb-1">Instructions</label>
        <textarea
          value={(data as any).instructions ?? ""}
          onChange={(e) => updateField("instructions", e.target.value)}
          data-testid="agent-instructions-input"
          rows={4}
          className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded-md focus:outline-none focus:ring-1 focus:ring-indigo-400 focus:border-indigo-400 resize-none"
          placeholder="Instructions for the agent..."
        />
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-500 mb-1">Model</label>
        <input
          type="text"
          list="model-suggestions"
          value={(data as any).modelName ?? "ollama:llama3.1"}
          onChange={(e) => updateField("modelName", e.target.value)}
          data-testid="agent-model-input"
          className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded-md focus:outline-none focus:ring-1 focus:ring-indigo-400 focus:border-indigo-400"
          placeholder="e.g. ollama:gemma4:31b"
        />
        <datalist id="model-suggestions">
          {MODEL_SUGGESTIONS.map((m) => (
            <option key={m} value={m} />
          ))}
        </datalist>
      </div>

      <div className="pt-4 border-t border-gray-100 space-y-3">
        <h4 className="text-xs font-semibold text-gray-600 mb-2">Capabilities</h4>

        <div>
          <label className="flex items-center gap-2 cursor-pointer">
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
              className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
            />
            <span className="text-xs font-medium text-gray-600">Enable Memory</span>
          </label>
          <p className="text-[10px] text-gray-400 ml-5">Agent stores and retrieves long-term memories</p>
        </div>

        {(data as any).agentType === "router" && (
          <div>
            <label className="flex items-center gap-2 cursor-pointer">
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
                className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
              />
              <span className="text-xs font-medium text-gray-600">Enable Conversation History</span>
            </label>
            <p className="text-[10px] text-gray-400 ml-5">Agent sees prior conversation turns</p>
          </div>
        )}

        <div className="pt-2 border-t border-gray-100">
        <h4 className="text-xs font-semibold text-gray-600 mb-2 flex items-center gap-1">
          <Wrench className="w-3 h-3" /> Connected Tools
        </h4>
        <div className="space-y-1">
          {connectedTools.length > 0 ? (
            connectedTools.map((tool) => (
              <div
                key={tool.id}
                className="flex items-center justify-between px-2 py-1 bg-amber-50 text-amber-700 rounded border border-amber-100 text-[11px] font-medium"
              >
                <span className="truncate">{tool.data.name}</span>
                <button
                  onClick={() => selectNode(tool.id)}
                  className="text-amber-500 hover:text-amber-600 font-bold px-1"
                >
                  →
                </button>
              </div>
            ))
          ) : (
            <p className="text-[11px] text-gray-400 italic">No tools connected</p>
          )}
        </div>
      </div>
    </div>
    </div>
  );
}
