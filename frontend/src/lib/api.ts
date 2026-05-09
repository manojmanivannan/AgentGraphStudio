import type {
  CanvasListItem,
  CanvasResponse,
  CanvasSavePayload,
  Conversation,
  ConversationSummary,
} from "@/types";

const API_BASE = `http://${import.meta.env.VITE_API_HOST || "localhost:8000"}/api`;

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
  const res = await fetch(
    `${API_BASE}/canvases/${canvasId}/conversations`
  );
  if (!res.ok) throw new Error("Failed to list conversations");
  return res.json();
}

export async function getConversation(
  canvasId: string,
  conversationId: string
): Promise<Conversation> {
  const res = await fetch(
    `${API_BASE}/canvases/${canvasId}/conversations/${conversationId}`
  );
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
