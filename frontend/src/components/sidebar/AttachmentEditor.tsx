import { useEffect, useState } from "react";
import { useCanvasStore } from "@/store/canvasStore";

const CURATED_FILE_TYPES = [
  "csv",
  "json",
  "text",
  "python",
  "yaml",
  "image",
  "pdf",
  "binary",
] as const;

export function AttachmentEditor() {
  const selectedNodeId = useCanvasStore((s) => s.selectedNodeId);
  const nodes = useCanvasStore((s) => s.nodes);
  const setNodes = useCanvasStore((s) => s.setNodes);

  const selectedNode = nodes.find(
    (n) => n.id === selectedNodeId && n.type === "attachment"
  );

  const [localName, setLocalName] = useState("");
  const [localDescription, setLocalDescription] = useState("");
  const [selectValue, setSelectValue] = useState<string>("text");
  const [customFileType, setCustomFileType] = useState("");
  const [localDeliveryMethod, setLocalDeliveryMethod] = useState<string>("inline");

  useEffect(() => {
    if (selectedNode) {
      const data = selectedNode.data as any;
      setLocalName(data?.name ?? "");
      setLocalDescription(data?.description ?? "");
      setLocalDeliveryMethod(data?.deliveryMethod ?? "inline");
      const fileType = data?.fileType ?? "text";
      if ((CURATED_FILE_TYPES as readonly string[]).includes(fileType)) {
        setSelectValue(fileType);
        setCustomFileType("");
      } else {
        setSelectValue("other");
        setCustomFileType(fileType);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedNodeId]);

  if (!selectedNode) {
    return (
      <div className="flex items-center justify-center h-full text-[var(--color-text-tertiary)] text-[12px]">
        Select an attachment node to edit its properties
      </div>
    );
  }

  const updateStore = (field: string, value: string) => {
    const currentNodes = useCanvasStore.getState().nodes;
    const newNodes = currentNodes.map((n) =>
      n.id === selectedNodeId ? { ...n, data: { ...n.data, [field]: value } } : n
    );
    setNodes(newNodes);
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 pb-3 border-b border-[var(--color-border-subtle)]">
        <div className="w-5 h-5 rounded-md bg-[var(--color-success-subtle)] flex items-center justify-center">
          <svg className="w-3 h-3 text-[var(--color-success)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
          </svg>
        </div>
        <h3 className="text-[13px] font-semibold text-[var(--color-text-primary)]">Attachment Properties</h3>
      </div>

      <div>
        <label className="block text-[13px] font-semibold text-[var(--color-text-tertiary)] mb-1.5 uppercase tracking-[0.06em]">Name</label>
        <input
          type="text"
          value={localName}
          onChange={(e) => {
            setLocalName(e.target.value);
            updateStore("name", e.target.value);
          }}
          data-testid="attachment-name-input"
          className="input-base w-full"
          placeholder="Attachment name"
        />
      </div>

      <div>
        <label className="block text-[13px] font-semibold text-[var(--color-text-tertiary)] mb-1.5 uppercase tracking-[0.06em]">File Type</label>
        <select
          value={selectValue}
          onChange={(e) => {
            const value = e.target.value;
            setSelectValue(value);
            if (value === "other") {
              updateStore("fileType", customFileType);
            } else {
              setCustomFileType("");
              updateStore("fileType", value);
            }
          }}
          data-testid="attachment-file-type-select"
          className="input-base w-full"
        >
          {CURATED_FILE_TYPES.map((ft) => (
            <option key={ft} value={ft}>
              {ft}
            </option>
          ))}
          <option value="other">other…</option>
        </select>
        {selectValue === "other" && (
          <input
            type="text"
            value={customFileType}
            onChange={(e) => {
              setCustomFileType(e.target.value);
              updateStore("fileType", e.target.value);
            }}
            data-testid="attachment-file-type-custom-input"
            className="input-base w-full mt-1.5"
            placeholder="Custom file type"
          />
        )}
      </div>

      <div>
        <label className="block text-[13px] font-semibold text-[var(--color-text-tertiary)] mb-1.5 uppercase tracking-[0.06em]">Delivery Method</label>
        <select
          value={localDeliveryMethod}
          onChange={(e) => {
            setLocalDeliveryMethod(e.target.value);
            updateStore("deliveryMethod", e.target.value);
          }}
          data-testid="attachment-delivery-method-select"
          className="input-base w-full"
        >
          <option value="inline">Inline (text / image)</option>
          <option value="file_path">File path (sandbox)</option>
        </select>
        <p className="mt-1 text-[12px] text-[var(--color-text-tertiary)]">
          Preference for how this attachment is delivered to the consuming agent. The framework falls back automatically when this isn't feasible (e.g. binary/pdf content, or no sandbox available).
        </p>
      </div>

      <div>
        <label className="block text-[13px] font-semibold text-[var(--color-text-tertiary)] mb-1.5 uppercase tracking-[0.06em]">Description</label>
        <textarea
          value={localDescription}
          onChange={(e) => {
            setLocalDescription(e.target.value);
            updateStore("description", e.target.value);
          }}
          data-testid="attachment-description-input"
          className="input-base w-full resize-none"
          rows={4}
          placeholder="Optional description"
        />
      </div>
    </div>
  );
}
