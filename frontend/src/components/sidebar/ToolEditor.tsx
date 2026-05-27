import { useState, useEffect, useRef } from "react";
import Editor from "@monaco-editor/react";
import { useCanvasStore } from "@/store/canvasStore";

export function ToolEditor() {
  const selectedNodeId = useCanvasStore((s) => s.selectedNodeId);
  const nodes = useCanvasStore((s) => s.nodes);
  const setNodes = useCanvasStore((s) => s.setNodes);

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
      <div className="flex items-center justify-center h-full text-gray-400 text-sm">
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
      <h3 className="text-sm font-semibold text-gray-700 border-b pb-2">Tool Properties</h3>

      <div className="flex items-center justify-between p-2 bg-amber-50 rounded border border-amber-100 mb-3">
        <span className="text-[11px] font-semibold text-amber-700 uppercase tracking-wider">
          Inferred Arguments
        </span>
        <div className="flex gap-1">
          {args.length > 0 ? (
            args.map((arg) => (
              <span key={arg} className="px-1.5 py-0.5 bg-white border border-amber-200 text-amber-600 rounded text-[10px] font-mono">
                {arg}
              </span>
            ))
          ) : (
            <span className="text-[10px] text-amber-400 italic">None detected</span>
          )}
        </div>
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-500 mb-1">Name</label>
        <input
          type="text"
          value={localName}
          onChange={(e) => {
            setLocalName(e.target.value);
            updateStore("name", e.target.value);
          }}
          data-testid="tool-name-input"
          className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded-md focus:outline-none focus:ring-1 focus:ring-amber-400 focus:border-amber-400"
          placeholder="Tool name"
        />
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-500 mb-1">Python Code</label>
        <div className="border border-gray-200 rounded-md overflow-hidden h-[300px]">
          <Editor
            height="300px"
            defaultLanguage="python"
            value={localCode}
            onChange={(value) => {
              setLocalCode(value ?? "");
              updateStore("code", value ?? "");
            }}
            theme="vs-light"
            wrapperProps={{ "data-testid": "tool-code-editor" }}
            options={{
              minimap: { enabled: false },
              fontSize: 13,
              lineNumbers: "on",
              scrollBeyondLastLine: false,
              wordWrap: "on",
              automaticLayout: true,
            }}
          />
        </div>
      </div>
    </div>
  );
}
