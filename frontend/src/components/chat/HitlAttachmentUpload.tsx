import { useRef, useState } from "react";
import { Check, Loader2, Paperclip } from "lucide-react";
import { uploadChatAttachments } from "@/lib/api";

interface HitlAttachmentUploadProps {
  conversationId: string;
  agentNodeId?: string | null;
}

type UploadState =
  | { status: "idle" }
  | { status: "uploading"; filename: string }
  | { status: "success"; filename: string }
  | { status: "error"; filename: string; message: string };

export function HitlAttachmentUpload({
  conversationId,
  agentNodeId,
}: HitlAttachmentUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploadState, setUploadState] = useState<UploadState>({ status: "idle" });

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setUploadState({ status: "uploading", filename: file.name });

    try {
      const [result] = await uploadChatAttachments(
        conversationId,
        [file],
        agentNodeId ?? undefined
      );

      if (!result?.success) {
        setUploadState({
          status: "error",
          filename: file.name,
          message: result?.error ?? "Failed to upload attachment",
        });
        return;
      }

      setUploadState({ status: "success", filename: file.name });
    } catch (error) {
      console.error("Failed to upload HITL attachment:", error);
      setUploadState({
        status: "error",
        filename: file.name,
        message: "Failed to upload attachment",
      });
    } finally {
      event.target.value = "";
    }
  };

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={uploadState.status === "uploading"}
          aria-label="Upload attachment"
          title="Upload attachment"
          className="inline-flex items-center justify-center w-8 h-8 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-base)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:border-[var(--color-accent)] transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {uploadState.status === "uploading" ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Paperclip className="w-4 h-4" />
          )}
        </button>

        {uploadState.status === "uploading" && (
          <span className="text-[13px] text-[var(--color-text-secondary)]">
            Uploading {uploadState.filename}...
          </span>
        )}

        {uploadState.status === "success" && (
          <span className="inline-flex items-center gap-1.5 text-[13px] font-medium text-[var(--color-success)]">
            <Check className="w-3.5 h-3.5" />
            <span>Uploaded {uploadState.filename}</span>
          </span>
        )}
      </div>

      {uploadState.status === "error" && (
        <p className="text-[13px] text-[var(--color-danger)]">{uploadState.message}</p>
      )}

      <input
        ref={inputRef}
        type="file"
        onChange={handleFileChange}
        data-testid="hitl-attachment-input"
        className="hidden"
      />
    </div>
  );
}
