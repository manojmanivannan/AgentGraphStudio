import { useState, useEffect, useRef } from "react";
import Editor from "@monaco-editor/react";
import { useCanvasStore } from "@/store/canvasStore";
import { useThemeStore } from "@/store/themeStore";

export function ToolEditor() {
  const selectedNodeId = useCanvasStore((s) => s.selectedNodeId);
  const nodes = useCanvasStore((s) => s.nodes);
  const setNodes = useCanvasStore((s) => s.setNodes);
  const theme = useThemeStore((s) => s.theme);
  const editorTheme = theme === "dark" ? "vs-dark" : "light";

  const selectedNode = nodes.find((n) => n.id === selectedNodeId && n.type === "tool");

  const [localName, setLocalName] = useState("");
  const [localCode, setLocalCode] = useState("");

  useEffect(() => {
    if (selectedNode) {
      setLocalName((selectedNode.data as any)?.name ?? "");
      setLocalCode((selectedNode.data as any)?.code ?? "");
    }
  }, [selectedNodeId]);

  if (!selectedNode) {
    return (
      <div className="flex items-center justify-center h-full text-[var(--color-text-tertiary)] text-[12px]">
        Select a tool node to edit its code
      </div>
    );
  }

  // Simple regex to extract function arguments from the code for preview
  const extractArgs = (code: string) => {
    const match = code.match(/def\s+\w+\s*\(([^)]*)\):/);
    if (!match) return [];
    return match[1]
      .split(",")
      .map((arg) => arg.trim())
      .filter((arg) => arg !== "");
  };

  const args = extractArgs(localCode);

  const updateStore = (field: string, value: string) => {
    const currentNodes = useCanvasStore.getState().nodes;
    const newNodes = currentNodes.map((n) =>
      n.id === selectedNodeId
        ? { ...n, data: { ...n.data, [field]: value } }
        : n
    );
    setNodes(newNodes);
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 pb-3 border-b border-[var(--color-border-subtle)]">
        <div className="w-5 h-5 rounded-md bg-[var(--color-secondary-subtle)] flex items-center justify-center">
          <svg className="w-3 h-3 text-[var(--color-secondary)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
          </svg>
        </div>
        <h3 className="text-[13px] font-semibold text-[var(--color-text-primary)]">Tool Properties</h3>
      </div>

      <div className="flex items-center justify-between p-2.5 bg-[var(--color-secondary-surface)] border border-[var(--color-secondary)]/15 rounded-lg">
        <span className="text-[10px] font-semibold text-[var(--color-secondary)] uppercase tracking-[0.1em]">
          Inferred Arguments
        </span>
        <div className="flex gap-1">
          {args.length > 0 ? (
            args.map((arg) => (
              <span key={arg} className="px-1.5 py-0.5 bg-[var(--color-base)] border border-[var(--color-secondary)]/20 text-[var(--color-secondary)] rounded text-[10px] font-[var(--font-mono)]">
                {arg}
              </span>
            ))
          ) : (
            <span className="text-[10px] text-[var(--color-text-tertiary)] italic">None detected</span>
          )}
        </div>
      </div>

      <div>
        <label className="block text-[11px] font-semibold text-[var(--color-text-tertiary)] mb-1.5 uppercase tracking-[0.06em]">Name</label>
        <input
          type="text"
          value={localName}
          onChange={(e) => {
            setLocalName(e.target.value);
            updateStore("name", e.target.value);
          }}
          data-testid="tool-name-input"
          className="input-base w-full"
          placeholder="Tool name"
        />
      </div>

      <div>
        <label className="block text-[11px] font-semibold text-[var(--color-text-tertiary)] mb-1.5 uppercase tracking-[0.06em]">Python Code</label>
        <div className="border border-[var(--color-border-default)] rounded-lg overflow-hidden h-[300px]">
          <Editor
            height="300px"
            defaultLanguage="python"
            value={localCode}
            onChange={(value) => {
              setLocalCode(value ?? "");
              updateStore("code", value ?? "");
            }}
            theme={editorTheme}
            wrapperProps={{ "data-testid": "tool-code-editor" }}
            options={{
              minimap: { enabled: false },
              fontSize: 13,
              fontFamily: "JetBrains Mono, monospace",
              lineNumbers: "on",
              scrollBeyondLastLine: false,
              wordWrap: "on",
              automaticLayout: true,
              padding: { top: 8 },
              renderLineHighlight: "gutter",
              bracketPairColorization: { enabled: true },
            }}
          />
        </div>
      </div>
    </div>
  );
}