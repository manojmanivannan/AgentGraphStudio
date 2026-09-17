import { vi } from "vitest";

/**
 * Intercept chat-attachment uploads by stubbing the global fetch directly.
 *
 * MSW handlers cannot reliably parse multipart bodies in this environment:
 * Node's native fetch serializes jsdom FormData/File values through its
 * internal undici, which mangles File entries (default filename "blob", empty
 * content) and makes `request.formData()` throw. Upload tests therefore assert
 * on the FormData object handed to fetch instead. Any request that is not an
 * attachment upload is delegated to the previous fetch implementation (MSW's
 * patched one), so the rest of the test keeps using MSW handlers.
 */
export function interceptAttachmentUpload(
  handler: (url: string, formData: FormData) => Response | Promise<Response>,
): void {
  const previousFetch = globalThis.fetch;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url =
        input instanceof URL ? input.href : typeof input === "string" ? input : input.url;
      if (url.includes("/attachments") && init?.body instanceof FormData) {
        return handler(url, init.body as FormData);
      }
      return previousFetch(input, init);
    }),
  );
}

/** Build the JSON response shape `uploadChatAttachments` expects. */
export function jsonAttachmentUploadResponse(
  results: Array<{
    filename: string;
    success: boolean;
    attachment_id?: string | null;
    node_id?: string | null;
    file_type?: string | null;
    error?: string | null;
  }>,
): Response {
  return new Response(JSON.stringify({ results }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}