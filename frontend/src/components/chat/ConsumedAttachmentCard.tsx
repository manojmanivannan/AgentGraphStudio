import { Download } from "lucide-react";

import { API_BASE } from "@/lib/api";

import { getAttachmentIcon, normalizeFileType, withFileExtension } from "./ProducedAttachmentCard";

interface ConsumedAttachmentCardProps {
  name: string;
  fileType: string;
  deliveryMethod: string;
  attachmentId: string;
  originalFilename?: string | null;
}

export function ConsumedAttachmentCard({
  name,
  fileType,
  deliveryMethod,
  attachmentId,
  originalFilename,
}: ConsumedAttachmentCardProps) {
  const previewUrl = `${API_BASE}/attachments/${attachmentId}`;
  const isImage = normalizeFileType(fileType) === "image";
  const showThumbnail = isImage && (deliveryMethod === "dual" || deliveryMethod === "inline");
  const showPathBadge = deliveryMethod === "file_path" || deliveryMethod === "dual";
  const showManifestNote = deliveryMethod === "manifest_only";
  // The uploaded filename (e.g. "city_name.json") is the file's real
  // identity; `name` is only the declared Attachment node's canvas label
  // (e.g. "CityName") — #90. Show the node label in brackets alongside it
  // only when there is one to distinguish from (agent-produced attachments
  // consumed downstream have no upload filename at all).
  const displayName = originalFilename || withFileExtension(name, fileType);
  const showNodeLabel = Boolean(originalFilename) && originalFilename !== name;

  return (
    <div className="rounded-lg border border-[var(--color-info)]/20 bg-[var(--color-base)] px-3 py-2 text-[var(--color-text-primary)]">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--color-info-subtle)] text-[var(--color-info)]">
            {getAttachmentIcon(fileType)}
          </span>
          <div className="min-w-0">
            <div className="truncate text-[12px] font-medium text-[var(--color-text-primary)]">
              {displayName}
              {showNodeLabel && (
                <span
                  data-testid="attachment-node-label"
                  className="ml-1 font-normal text-[var(--color-text-tertiary)]"
                >
                  ({name})
                </span>
              )}
            </div>
            <div className="text-[10px] uppercase tracking-wide text-[var(--color-text-tertiary)]">
              {fileType} · input
            </div>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {showPathBadge && (
            <span
              data-testid="attachment-path-badge"
              className="inline-flex items-center gap-1 rounded-md border border-[var(--color-border-default)] bg-[var(--color-elevated)] px-2 py-1 text-[10px] font-semibold text-[var(--color-text-secondary)]"
            >
              📁 file path
            </span>
          )}
          <a
            href={previewUrl}
            download={displayName}
            className="inline-flex items-center gap-1.5 rounded-md border border-[var(--color-border-default)] bg-[var(--color-elevated)] px-2.5 py-1.5 text-[11px] font-semibold text-[var(--color-accent)] transition-colors hover:border-[var(--color-accent)] hover:text-[var(--color-accent-bright)]"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Download</span>
          </a>
        </div>
      </div>
      {showThumbnail && (
        <img
          src={previewUrl}
          alt={displayName}
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
