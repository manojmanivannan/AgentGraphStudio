/**
 * @fileoverview Renders agent message content as markdown (final answers,
 * execution-step messages, HITL prompts).
 *
 * Uses react-markdown (raw HTML is skipped by default, so model output can
 * never inject markup) with remark-gfm for tables/strikethrough/task lists.
 * The memo wrapper matters during streaming: the assistant's final answer
 * re-renders on every token, and ReactMarkdown's parse is pure w.r.t. the
 * content string.
 */

import { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { apiOrigin } from "@/lib/api";

interface MarkdownMessageProps {
  content: string;
  /** Smaller typography for execution-step messages (the `isSmall` flag
   * threaded through `renderMessageContent`). */
  small?: boolean;
}

/** Resolves backend-relative image URLs (e.g. `/api/attachments/…`) against
 * the API origin — same behavior the old regex renderer had in ChatPage. */
function resolveImageUrl(src?: string): string {
  if (!src) return "";
  if (src.startsWith("/")) return `${apiOrigin}${src}`;
  return src;
}

export const MarkdownMessage = memo(function MarkdownMessage({
  content,
  small = false,
}: MarkdownMessageProps) {
  if (!content) return null;

  return (
    <div className={small ? "chat-markdown chat-markdown--sm" : "chat-markdown"}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ node: _node, ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer" />
          ),
          img: ({ node: _node, src, alt, ...props }) => (
            <img
              {...props}
              src={resolveImageUrl(typeof src === "string" ? src : "")}
              alt={alt ?? ""}
              loading="lazy"
            />
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
});