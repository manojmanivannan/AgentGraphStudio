import { useState, useEffect } from "react";
import { useCanvasStore } from "@/store/canvasStore";
import { Wrench, Plus, Loader2, FileText, Trash2 } from "lucide-react";
import { listAgentDocuments, uploadAgentDocument, deleteAgentDocument } from "@/lib/api";
import type { AgentDocument } from "@/types";
import { InfoTooltip } from "./InfoTooltip";

export function AgentEditor() {
  const selectedNodeId = useCanvasStore((s) => s.selectedNodeId);
  const nodes = useCanvasStore((s) => s.nodes);
  const setNodes = useCanvasStore((s) => s.setNodes);
  const canvasId = useCanvasStore((s) => s.canvasId);

  const [documents, setDocuments] = useState<AgentDocument[]>([]);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [uploading, setUploading] = useState(false);

  const selectedNode = nodes.find((n) => n.id === selectedNodeId && n.type === "agent");

  const data = selectedNode?.data ?? {};

  // Fetch agent RAG documents when RAG is enabled
  useEffect(() => {
    if (!canvasId || !selectedNodeId || !(data as any).enableRag) {
      setDocuments([]);
      return;
    }
    let active = true;
    const loadDocs = async () => {
      setLoadingDocs(true);
      try {
        const docs = await listAgentDocuments(canvasId, selectedNodeId);
        if (active) setDocuments(docs);
      } catch (err) {
        console.error("Failed to load documents:", err);
      } finally {
        if (active) setLoadingDocs(false);
      }
    };
    loadDocs();
    return () => {
      active = false;
    };
  }, [canvasId, selectedNodeId, (data as any).enableRag]);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0 || !canvasId || !selectedNodeId) return;
    setUploading(true);
    try {
      const doc = await uploadAgentDocument(canvasId, selectedNodeId, files[0]);
      setDocuments((prev) => [doc, ...prev]);
    } catch (err) {
      console.error("Failed to upload document:", err);
      alert("Failed to upload document");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  const handleDeleteDoc = async (docId: string) => {
    if (!canvasId || !selectedNodeId) return;
    if (!confirm("Are you sure you want to delete this document?")) return;
    try {
      await deleteAgentDocument(canvasId, selectedNodeId, docId);
      setDocuments((prev) => prev.filter((d) => d.id !== docId));
    } catch (err) {
      console.error("Failed to delete document:", err);
      alert("Failed to delete document");
    }
  };

  if (!selectedNode) {
    return (
      <div className="flex items-center justify-center h-full text-[var(--color-text-tertiary)] text-[12px]">
        Select an agent node to edit its properties
      </div>
    );
  }

  const updateField = (field: string, value: string) => {
    const updatedNodes = nodes.map((n) =>
      n.id === selectedNodeId
        ? { ...n, data: { ...n.data, [field]: value } }
        : n
    );
    setNodes(updatedNodes);
  };

  const handleAgentTypeChange = (value: string) => {
    const updatedNodes = nodes.map((n) => {
      if (n.id === selectedNodeId) {
        const newData = { ...n.data, agentType: value } as any;
        if (value === "router") {
          newData.enablePlotting = false;
        }
        return { ...n, data: newData };
      }
      return n;
    });
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
            <path d="M12 2a4 4 0 0 1 4 4v1a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z" />
            <path d="M12 12c-4 0-7 2-7 5v2h14v-2c0-3-3-5-7-5z" />
          </svg>
        </div>
        <h3 className="text-[13px] font-semibold text-[var(--color-text-primary)]">Agent Properties</h3>
      </div>

      <div>
        <label className="block text-[11px] font-semibold text-[var(--color-text-tertiary)] mb-1.5 uppercase tracking-[0.06em]">Type</label>
        <select
          value={(data as any).agentType ?? "worker"}
          onChange={(e) => handleAgentTypeChange(e.target.value)}
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
        <div className="mb-1.5 flex items-center gap-1.5">
          <label className="text-[11px] font-semibold text-[var(--color-text-tertiary)] uppercase tracking-[0.06em]">Instructions</label>
          {(data as any).agentType === "worker" && (
            <InfoTooltip
              testId="agent-instructions-info"
              ariaLabel="Worker instructions tips"
              content="In order to use rag context, use {{ rag_document }} which will dyanamically replaced by retrieved content. Note: it is hard coded with top 5 results"
            />
          )}
        </div>
        <textarea
          value={(data as any).instructions ?? ""}
          onChange={(e) => updateField("instructions", e.target.value)}
          data-testid="agent-instructions-input"
          rows={4}
          className="input-base w-full resize-none"
          placeholder="Instructions for the agent..."
        />
      </div>

      <div className="pt-4 border-t border-[var(--color-border-subtle)] space-y-3">
        <h4 className="text-[11px] font-semibold text-[var(--color-text-tertiary)] uppercase tracking-[0.06em]">Capabilities</h4>

        <div>
          <label className="flex items-center gap-2.5 cursor-pointer group">
            <input
              type="checkbox"
              checked={(data as any).isEntryPoint ?? false}
              onChange={(e) => {
                const checked = e.target.checked;
                if (checked) {
                  const otherEntryPointAgent = nodes.find(
                    (n) =>
                      n.id !== selectedNodeId &&
                      n.type === "agent" &&
                      n.data?.isEntryPoint === true
                  );
                  if (otherEntryPointAgent) {
                    alert(`Agent '${otherEntryPointAgent.data.name}' is already selected as the entry point.`);
                    return;
                  }
                }
                const updatedNodes = nodes.map((n) =>
                  n.id === selectedNodeId
                    ? { ...n, data: { ...n.data, isEntryPoint: checked } }
                    : n
                );
                setNodes(updatedNodes);
              }}
              data-testid="agent-is-entry-point"
              className="rounded border-[var(--color-border-default)] text-[var(--color-accent)] focus:ring-[var(--color-accent)] bg-[var(--color-base)]"
            />
            <div>
              <span className="text-[12px] font-medium text-[var(--color-text-secondary)] group-hover:text-[var(--color-text-primary)] transition-colors">Entry Point</span>
              <p className="text-[10px] text-[var(--color-text-tertiary)] mt-0.5">Designate this agent as the conversation entry point</p>
            </div>
          </label>
        </div>

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

        {(data as any).agentType !== "router" && (
          <div>
            <label className="flex items-center gap-2.5 cursor-pointer group">
              <input
                type="checkbox"
                checked={(data as any).enablePlotting ?? false}
                onChange={(e) => {
                  const checked = e.target.checked;
                  const updatedNodes = nodes.map((n) =>
                    n.id === selectedNodeId
                      ? { ...n, data: { ...n.data, enablePlotting: checked } }
                      : n
                  );
                  setNodes(updatedNodes);
                }}
                data-testid="agent-enable-plotting"
                className="rounded border-[var(--color-border-default)] text-[var(--color-accent)] focus:ring-[var(--color-accent)] bg-[var(--color-base)]"
              />
              <div>
                <span className="text-[12px] font-medium text-[var(--color-text-secondary)] group-hover:text-[var(--color-text-primary)] transition-colors">Enable Plotting</span>
                <p className="text-[10px] text-[var(--color-text-tertiary)] mt-0.5">Agent can generate charts and plots</p>
              </div>
            </label>
          </div>
        )}

        {(data as any).agentType === "worker" && (
          <div>
            <label className="flex items-center gap-2.5 cursor-pointer group">
              <input
                type="checkbox"
                checked={(data as any).enableHitl ?? false}
                onChange={(e) => {
                  const checked = e.target.checked;
                  const updatedNodes = nodes.map((n) =>
                    n.id === selectedNodeId
                      ? { ...n, data: { ...n.data, enableHitl: checked } }
                      : n
                  );
                  setNodes(updatedNodes);
                }}
                data-testid="agent-enable-hitl"
                className="rounded border-[var(--color-border-default)] text-[var(--color-accent)] focus:ring-[var(--color-accent)] bg-[var(--color-base)]"
              />
              <div>
                <span className="text-[12px] font-medium text-[var(--color-text-secondary)] group-hover:text-[var(--color-text-primary)] transition-colors">Enable Human-in-the-Loop</span>
                <p className="text-[10px] text-[var(--color-text-tertiary)] mt-0.5">Let agent ask for clarification or input</p>
              </div>
            </label>
          </div>
        )}


        {(data as any).agentType === "worker" && (
          <div>
            <label className="flex items-center gap-2.5 cursor-pointer group">
              <input
                type="checkbox"
                checked={(data as any).enableRag ?? false}
                onChange={(e) => {
                  const checked = e.target.checked;
                  const updatedNodes = nodes.map((n) =>
                    n.id === selectedNodeId
                      ? { ...n, data: { ...n.data, enableRag: checked } }
                      : n
                  );
                  setNodes(updatedNodes);
                }}
                data-testid="agent-enable-rag"
                className="rounded border-[var(--color-border-default)] text-[var(--color-accent)] focus:ring-[var(--color-accent)] bg-[var(--color-base)]"
              />
              <div>
                <span className="text-[12px] font-medium text-[var(--color-text-secondary)] group-hover:text-[var(--color-text-primary)] transition-colors">Enable RAG Documents</span>
                <p className="text-[10px] text-[var(--color-text-tertiary)] mt-0.5">Substitute retrieved documents into prompt</p>
              </div>
            </label>

            {(data as any).enableRag && (
              <div className="mt-3 pl-7 space-y-3 border-l border-[var(--color-border-subtle)]">
                <div>
                  <label className="block text-[10px] font-semibold text-[var(--color-text-tertiary)] mb-1 uppercase tracking-[0.06em]">Chunk Size (tokens)</label>
                  <input
                    type="number"
                    value={(data as any).ragChunkSize ?? 1000}
                    onChange={(e) => {
                      const val = parseInt(e.target.value) || 1000;
                      const updatedNodes = nodes.map((n) =>
                        n.id === selectedNodeId
                          ? { ...n, data: { ...n.data, ragChunkSize: val } }
                          : n
                      );
                      setNodes(updatedNodes);
                    }}
                    className="input-base w-full"
                    min={100}
                    max={10000}
                  />
                </div>

                <div className="space-y-2 pt-1">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-semibold text-[var(--color-text-tertiary)] uppercase tracking-[0.06em]">Documents</span>
                    <label className="text-[11px] text-[var(--color-accent)] hover:text-[var(--color-accent-bright)] cursor-pointer flex items-center gap-1 font-medium transition-colors">
                      {uploading ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <Plus className="w-3 h-3" />
                      )}
                      <span>{uploading ? "Uploading..." : "Upload File"}</span>
                      <input
                        type="file"
                        accept=".txt,.md,.json"
                        onChange={handleFileUpload}
                        className="hidden"
                        disabled={uploading}
                      />
                    </label>
                  </div>

                  <div className="space-y-1 max-h-[150px] overflow-y-auto pr-1">
                    {loadingDocs ? (
                      <p className="text-[11px] text-[var(--color-text-tertiary)] italic">Loading documents...</p>
                    ) : documents.length > 0 ? (
                      documents.map((doc) => (
                        <div key={doc.id} className="flex items-center justify-between px-2 py-1.5 bg-[var(--color-secondary-surface)]/20 border border-[var(--color-border-subtle)] rounded-lg text-[11px] text-[var(--color-text-secondary)]">
                          <span className="truncate flex items-center gap-1.5 max-w-[80%]">
                            <FileText className="w-3.5 h-3.5 text-[var(--color-text-tertiary)] flex-shrink-0" />
                            <span className="truncate" title={doc.name}>{doc.name}</span>
                          </span>
                          <button
                            onClick={() => handleDeleteDoc(doc.id)}
                            className="text-[var(--color-text-tertiary)] hover:text-red-500 hover:bg-red-500/10 p-1 rounded-md transition-colors"
                          >
                            <Trash2 className="w-3 h-3" />
                          </button>
                        </div>
                      ))
                    ) : (
                      <p className="text-[11px] text-[var(--color-text-tertiary)] italic">No documents uploaded.</p>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

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
                  <span className="truncate">{(tool.data as any)?.name}</span>
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