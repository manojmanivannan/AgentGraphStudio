import {
  Download,
  File,
  FileCode,
  FileImage,
  FileJson,
  FileText,
} from "lucide-react";

import { API_BASE } from "@/lib/api";

interface ProducedAttachmentCardProps {
  name: string;
  fileType: string;
  attachmentId: string;
  originalFilename?: string | null;
}

export function normalizeFileType(fileType: string) {
  return fileType.trim().toLowerCase();
}

// Mirrors backend's `output_extraction._FILE_TYPE_TO_FORMAT` (#90): a
// declared/inferred file_type maps to a storage extension. Unknown/freeform
// file types fall back to "bin".
const FILE_TYPE_TO_EXTENSION: Record<string, string> = {
  text: "txt",
  csv: "csv",
  json: "json",
  python: "py",
  yaml: "yaml",
  pdf: "pdf",
  image: "png",
  binary: "bin",
};

/** Appends a file_type-derived extension to `name` unless it already has one. */
export function withFileExtension(name: string, fileType: string) {
  const ext = FILE_TYPE_TO_EXTENSION[normalizeFileType(fileType)] ?? "bin";
  return name.toLowerCase().endsWith(`.${ext}`) ? name : `${name}.${ext}`;
}

export function getAttachmentIcon(fileType: string) {
  const normalizedType = normalizeFileType(fileType);

  if (normalizedType === "image") {
    return <FileImage className="w-4 h-4" data-testid="attachment-icon-image" />;
  }

  if (normalizedType === "json") {
    return <FileJson className="w-4 h-4" data-testid="attachment-icon-json" />;
  }

  if (normalizedType === "python" || normalizedType === "yaml") {
    return <FileCode className="w-4 h-4" data-testid={`attachment-icon-${normalizedType}`} />;
  }

  if (normalizedType === "csv" || normalizedType === "text" || normalizedType === "pdf") {
    return <FileText className="w-4 h-4" data-testid={`attachment-icon-${normalizedType}`} />;
  }

  return <File className="w-4 h-4" data-testid="attachment-icon-generic" />;
}

export function ProducedAttachmentCard({
  name,
  fileType,
  attachmentId,
  originalFilename,
}: ProducedAttachmentCardProps) {
  const downloadUrl = `${API_BASE}/attachments/${attachmentId}`;
  const isImageAttachment = normalizeFileType(fileType) === "image";
  const displayName = originalFilename || withFileExtension(name, fileType);

  return (
    <div className="rounded-lg border border-[var(--color-success)]/20 bg-[var(--color-base)] px-3 py-2 text-[var(--color-text-primary)]">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--color-success-subtle)] text-[var(--color-success)]">
            {getAttachmentIcon(fileType)}
          </span>
          <div className="min-w-0">
            <div className="truncate text-[12px] font-medium text-[var(--color-text-primary)]">
              {displayName}
            </div>
            <div className="text-[10px] uppercase tracking-wide text-[var(--color-text-tertiary)]">
              {fileType}
            </div>
          </div>
        </div>

        <a
          href={downloadUrl}
          download={displayName}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-[var(--color-border-default)] bg-[var(--color-elevated)] px-2.5 py-1.5 text-[11px] font-semibold text-[var(--color-accent)] transition-colors hover:border-[var(--color-accent)] hover:text-[var(--color-accent-bright)]"
        >
          <Download className="w-3.5 h-3.5" />
          <span>Download</span>
        </a>
      </div>

      {isImageAttachment ? (
        <img
          src={downloadUrl}
          alt={displayName}
          data-testid="attachment-thumbnail-image"
          className="mt-3 max-h-64 max-w-full rounded border border-[var(--color-border-subtle)] object-contain shadow-sm"
        />
      ) : null}
    </div>
  );
}
