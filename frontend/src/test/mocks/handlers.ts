import { http, HttpResponse } from "msw";
import type {
  CanvasResponse,
  CanvasListItem,
  CanvasSavePayload,
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

export const handlers = [
  http.get(`${API}/canvases`, () =>
    HttpResponse.json([mockCanvasListItem()])
  ),

  http.post(`${API}/canvases`, async ({ request }) => {
    const body = (await request.json()) as { name?: string };
    return HttpResponse.json(mockCanvas({ name: body.name ?? "Untitled Canvas" }), { status: 201 });
  }),

  http.get(`${API}/canvases/:id`, ({ params }) =>
    HttpResponse.json(mockCanvas({ id: params.id as string }))
  ),

  http.put(`${API}/canvases/:id`, async ({ params, request }) => {
    const body = (await request.json()) as CanvasSavePayload;
    return HttpResponse.json(mockCanvas({ id: params.id as string, name: body.name }));
  }),

  http.delete(`${API}/canvases/:id`, () => new HttpResponse(null, { status: 204 })),
];
