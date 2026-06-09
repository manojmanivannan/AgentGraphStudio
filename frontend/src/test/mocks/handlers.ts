import { http, HttpResponse } from "msw";
import type {
  CanvasResponse,
  CanvasListItem,
  CanvasSavePayload,
  Conversation,
  ConversationSummary,
} from "@/types";

const API = "http://localhost:8000/api";

export const mockCanvas = (overrides?: Partial<CanvasResponse>): CanvasResponse => ({
  id: "canvas-1",
  name: "Untitled Canvas",
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
  nodes: { agents: [], tools: [] },
  edges: [],
  ...overrides,
});

export const mockCanvasListItem = (overrides?: Partial<CanvasListItem>): CanvasListItem => ({
  id: "canvas-1",
  name: "Untitled Canvas",
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
  ...overrides,
});

export const mockConversation = (overrides?: Partial<Conversation>): Conversation => ({
  id: "conv-1",
  canvas_id: "canvas-1",
  name: "New Conversation",
  status: "active",
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
  messages: [],
  ...overrides,
});

export const mockConversationSummary = (overrides?: Partial<ConversationSummary>): ConversationSummary => ({
  id: "conv-1",
  canvas_id: "canvas-1",
  name: "New Conversation",
  status: "active",
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
  ...overrides,
});

export const handlers = [
  // Canvas CRUD
  http.get(`${API}/canvases`, () =>
    HttpResponse.json([mockCanvasListItem()])
  ),

  http.post(`${API}/canvases`, async ({ request }) => {
    const body = (await request.json()) as { name?: string };
    return HttpResponse.json(mockCanvas({ name: body.name ?? "Untitled Canvas" }), { status: 201 });
  }),

  // Import canvas — must come before :id route to avoid ambiguity
  http.post(`${API}/canvases/import`, async ({ request }) => {
    const body = (await request.json()) as CanvasSavePayload;
    return HttpResponse.json(
      mockCanvas({ id: "imported-1", name: body.name }),
      { status: 201 }
    );
  }),

  http.post(`${API}/canvases/import-zip`, async () => {
    return HttpResponse.json(
      mockCanvas({ id: "imported-zip", name: "Imported ZIP Canvas" }),
      { status: 201 }
    );
  }),

  http.get(`${API}/canvases/:id`, ({ params }) =>
    HttpResponse.json(mockCanvas({ id: params.id as string }))
  ),

  http.put(`${API}/canvases/:id`, async ({ params, request }) => {
    const body = (await request.json()) as CanvasSavePayload;
    return HttpResponse.json(mockCanvas({ id: params.id as string, name: body.name }));
  }),

  http.delete(`${API}/canvases/:id`, () => new HttpResponse(null, { status: 204 })),

  // Conversations
  http.get(`${API}/canvases/:canvasId/conversations`, () =>
    HttpResponse.json([])
  ),

  http.post(`${API}/canvases/:canvasId/conversations`, async ({ params, request }) => {
    const body = (await request.json()) as { name?: string };
    return HttpResponse.json(
      mockConversation({
        canvas_id: params.canvasId as string,
        name: body.name ?? "New Conversation",
      }),
      { status: 201 }
    );
  }),

  http.get(`${API}/canvases/:canvasId/conversations/:convId`, ({ params }) =>
    HttpResponse.json(
      mockConversation({
        id: params.convId as string,
        canvas_id: params.canvasId as string,
      })
    )
  ),

  http.delete(`${API}/canvases/:canvasId/conversations/:convId`, () =>
    new HttpResponse(null, { status: 204 })
  ),
];
