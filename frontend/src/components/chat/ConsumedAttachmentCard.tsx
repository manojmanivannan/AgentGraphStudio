import { API_BASE } from "@/lib/api";

import { getAttachmentIcon, normalizeFileType } from "./ProducedAttachmentCard";

interface ConsumedAttachmentCardProps {
  name: string;
  fileType: string;
  deliveryMethod: string;
  attachmentId: string;
}

export function ConsumedAttachmentCard({
  name,
  fileType,
  deliveryMethod,
  attachmentId,
}: ConsumedAttachmentCardProps) {
  const previewUrl = `${API_BASE}/attachments/${attachmentId}`;
  const isImage = normalizeFileType(fileType) === "image";
  const showThumbnail = isImage && (deliveryMethod === "dual" || deliveryMethod === "inline");
  const showPathBadge = deliveryMethod === "file_path" || deliveryMethod === "dual";
  const showManifestNote = deliveryMethod === "manifest_only";

  return (
    <div className="rounded-lg border border-[var(--color-info)]/20 bg-[var(--color-base)] px-3 py-2 text-[var(--color-text-primary)]">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--color-info-subtle)] text-[var(--color-info)]">
            {getAttachmentIcon(fileType)}
          </span>
          <div className="min-w-0">
            <div className="truncate text-[12px] font-medium text-[var(--color-text-primary)]">
              {name}
            </div>
            <div className="text-[10px] uppercase tracking-wide text-[var(--color-text-tertiary)]">
              {fileType} · input
            </div>
          </div>
        </div>
        {showPathBadge && (
          <span
            data-testid="attachment-path-badge"
            className="inline-flex shrink-0 items-center gap-1 rounded-md border border-[var(--color-border-default)] bg-[var(--color-elevated)] px-2 py-1 text-[10px] font-semibold text-[var(--color-text-secondary)]"
          >
            📁 file path
          </span>
        )}
      </div>
      {showThumbnail && (
        <img
          src={previewUrl}
          alt={name}
          data-testid="attachment-thumbnail-image"
          className="mt-3 max-h-64 max-w-full rounded border border-[var(--color-border-subtle)] object-contain shadow-sm"
        />
      )}
      {showManifestNote && (
        <div
          data-testid="attachment-manifest-note"
          className="mt-2 text-[11px] text-[var(--color-text-tertiary)] italic"
        >
          Not inlinable as text or an image, and no sandbox was available to materialize it as a file — the agent only received a manifest note.
        </div>
      )}
    </div>
  );
}
