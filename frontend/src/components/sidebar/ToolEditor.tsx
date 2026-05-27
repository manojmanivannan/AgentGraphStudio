import Editor from "@monaco-editor/react";
import { useCanvasStore } from "@/store/canvasStore";

export function ToolEditor() {
  const selectedNodeId = useCanvasStore((s) => s.selectedNodeId);
  const nodes = useCanvasStore((s) => s.nodes);
  const setNodes = useCanvasStore((s) => s.setNodes);

  const selectedNode = nodes.find((n) => n.id === selectedNodeId && n.type === "tool");

  if (!selectedNode) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400 text-sm">
        Select a tool node to edit its code
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

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold text-gray-700 border-b pb-2">Tool Properties</h3>

      <div>
        <label className="block text-xs font-medium text-gray-500 mb-1">Name</label>
        <input
          type="text"
          value={(data as any).name ?? ""}
          onChange={(e) => updateField("name", e.target.value)}
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
            value={(data as any).code ?? ""}
            onChange={(value) => updateField("code", value ?? "")}
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
