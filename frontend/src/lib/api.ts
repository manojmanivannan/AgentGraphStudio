import type {
  ActiveRunResponse,
  CanvasListItem,
  CanvasResponse,
  CanvasSavePayload,
  Conversation,
  ConversationSummary,
  ExecutionEvent,
  ToolInspectResponse,
  ToolTestResponse,
  AgentDocument,
} from "@/types";

const configuredApiHost = (import.meta.env.VITE_API_HOST as string | undefined)?.trim();
const defaultApiOrigin =
  typeof window !== "undefined"
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : "http://localhost:8000";

export const apiOrigin = configuredApiHost
  ? /^https?:\/\//.test(configuredApiHost)
    ? configuredApiHost
    : `http://${configuredApiHost}`
  : defaultApiOrigin;

const API_BASE = `${apiOrigin}/api`;

function isNetworkFetchError(error: unknown): error is Error {
  return error instanceof Error && /fetch|network|load failed|failed to fetch/i.test(error.message);
}

async function readErrorDetail(
  res: Response,
  fallbackMessage: string
): Promise<string> {
  const error = await res.json().catch(() => null) as { detail?: string } | null;
  return error?.detail || fallbackMessage;
}

export async function createCanvas(
  name = "Untitled Canvas"
): Promise<CanvasResponse> {
  const res = await fetch(`${API_BASE}/canvases`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error("Failed to create canvas");
  return res.json();
}

export async function listCanvases(): Promise<CanvasListItem[]> {
  const res = await fetch(`${API_BASE}/canvases`);
  if (!res.ok) throw new Error("Failed to list canvases");
  return res.json();
}

export async function getCanvas(id: string): Promise<CanvasResponse> {
  const res = await fetch(`${API_BASE}/canvases/${id}`);
  if (!res.ok) throw new Error("Failed to get canvas");
  return res.json();
}

export async function saveCanvas(
  id: string,
  payload: CanvasSavePayload
): Promise<CanvasResponse> {
  const res = await fetch(`${API_BASE}/canvases/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Failed to save canvas");
  return res.json();
}

export async function deleteCanvas(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/canvases/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete canvas");
}

export async function exportCanvas(id: string): Promise<CanvasResponse> {
  const res = await fetch(`${API_BASE}/canvases/${id}/export`);
  if (!res.ok) throw new Error("Failed to export canvas");
  return res.json();
}

export async function exportCanvasZip(id: string): Promise<Blob> {
  const res = await fetch(`${API_BASE}/canvases/${id}/export-zip`);
  if (!res.ok) throw new Error("Failed to export canvas ZIP");
  return res.blob();
}

export async function importCanvas(
  payload: CanvasSavePayload
): Promise<CanvasResponse> {
  const res = await fetch(`${API_BASE}/canvases/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Failed to import canvas");
  return res.json();
}

export async function importCanvasZip(file: File): Promise<CanvasResponse> {
  const createRequestInit = (): RequestInit => {
    const formData = new FormData();
    formData.append("file", file);
    return {
      method: "POST",
      body: formData,
    };
  };

  let res: Response;
  try {
    res = await fetch(`${API_BASE}/canvases/import-zip`, createRequestInit());
  } catch {

    try {
      res = await fetch(`/api/canvases/import-zip`, createRequestInit());
    } catch {
      throw new Error(
        "Failed to import canvas ZIP. Could not reach the backend import endpoint."
      );
    }
  }

  if (!res.ok) {
    if (res.status >= 500) {
      try {
        const fallbackRes = await fetch(`/api/canvases/import-zip`, createRequestInit());
        if (!fallbackRes.ok) {
          throw new Error(await readErrorDetail(fallbackRes, "Failed to import canvas ZIP"));
        }
        return fallbackRes.json();
      } catch (error) {
        if (!isNetworkFetchError(error)) throw error;
      }
    }

    throw new Error(await readErrorDetail(res, "Failed to import canvas ZIP"));
  }
  return res.json();
}

export async function createConversation(
  canvasId: string,
  name = "New Conversation"
): Promise<Conversation> {
  const res = await fetch(
    `${API_BASE}/canvases/${canvasId}/conversations`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }
  );
  if (!res.ok) throw new Error("Failed to create conversation");
  return res.json();
}

export async function listConversations(
  canvasId: string
): Promise<ConversationSummary[]> {
  const url = `${API_BASE}/canvases/${canvasId}/conversations?_=${Date.now()}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to list conversations");
  return res.json();
}

export async function getConversation(
  canvasId: string,
  conversationId: string
): Promise<Conversation> {
  const url = `${API_BASE}/canvases/${canvasId}/conversations/${conversationId}?_=${Date.now()}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to get conversation");
  return res.json();
}

export async function getConversationById(
  conversationId: string
): Promise<Conversation> {
  const url = `${API_BASE}/canvases/conversations/${conversationId}?_=${Date.now()}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to get conversation");
  return res.json();
}

export async function deleteConversation(
  canvasId: string,
  conversationId: string
): Promise<void> {
  const res = await fetch(
    `${API_BASE}/canvases/${canvasId}/conversations/${conversationId}`,
    { method: "DELETE" }
  );
  if (!res.ok) throw new Error("Failed to delete conversation");
}

export async function deleteConversationById(
  conversationId: string
): Promise<void> {
  const res = await fetch(
    `${API_BASE}/canvases/conversations/${conversationId}`,
    { method: "DELETE" }
  );
  if (!res.ok) throw new Error("Failed to delete conversation");
}

export async function inspectTool(
  code: string,
  dependencies?: string[]
): Promise<ToolInspectResponse> {
  const res = await fetch(`${API_BASE}/tools/inspect`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code, dependencies: dependencies ?? [] }),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Failed to inspect tool" }));
    throw new Error(error.detail || "Failed to inspect tool");
  }
  return res.json();
}

export async function testTool(
  code: string,
  args: Record<string, string>,
  dependencies?: string[]
): Promise<ToolTestResponse> {
  const res = await fetch(`${API_BASE}/tools/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code, args, dependencies: dependencies ?? [] }),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Failed to test tool" }));
    throw new Error(error.detail || "Failed to test tool");
  }
  return res.json();
}

export async function listAgentDocuments(
  canvasId: string,
  agentId: string
): Promise<AgentDocument[]> {
  const res = await fetch(`${API_BASE}/canvases/${canvasId}/agents/${agentId}/documents`);
  if (!res.ok) throw new Error("Failed to list agent documents");
  return res.json();
}

export async function uploadAgentDocument(
  canvasId: string,
  agentId: string,
  file: File
): Promise<AgentDocument> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(
    `${API_BASE}/canvases/${canvasId}/agents/${agentId}/documents`,
    {
      method: "POST",
      body: formData,
    }
  );
  if (!res.ok) throw new Error("Failed to upload agent document");
  return res.json();
}

export async function deleteAgentDocument(
  canvasId: string,
  agentId: string,
  documentId: string
): Promise<void> {
  const res = await fetch(
    `${API_BASE}/canvases/${canvasId}/agents/${agentId}/documents/${documentId}`,
    { method: "DELETE" }
  );
  if (!res.ok) throw new Error("Failed to delete agent document");
}

export async function exportConversationZip(
  canvasId: string,
  conversationId: string
): Promise<Blob> {
  const res = await fetch(
    `${API_BASE}/canvases/${canvasId}/conversations/${conversationId}/export`
  );
  if (!res.ok) throw new Error("Failed to export conversation ZIP");
  return res.blob();
}

export async function importConversationZip(
  canvasId: string,
  file: File
): Promise<Conversation> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(
    `${API_BASE}/canvases/${canvasId}/conversations/import`,
    {
      method: "POST",
      body: formData,
    }
  );
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Failed to import conversation" }));
    throw new Error(error.detail || "Failed to import conversation");
  }
  return res.json();
}

export async function getActiveRun(
  conversationId: string
): Promise<ActiveRunResponse | null> {
  const res = await fetch(`${API_BASE}/conversations/${conversationId}/runs/active`);
  if (!res.ok) throw new Error("Failed to get active run");
  return res.json();
}

export async function getRunEventsAfter(
  runId: string,
  afterSequence: number
): Promise<ExecutionEvent[]> {
  const params = new URLSearchParams({ after_sequence: String(afterSequence) });
  const res = await fetch(`${API_BASE}/runs/${runId}/events?${params.toString()}`);
  if (!res.ok) throw new Error("Failed to get run events");
  return res.json();
}
