import { afterEach, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "@/test/mocks/server";
import {
  createCanvas,
  listCanvases,
  getCanvas,
  saveCanvas,
  deleteCanvas,
  exportCanvas,
  exportCanvasZip,
  importCanvas,
  importCanvasZip,
  createConversation,
  listConversations,
  getConversation,
  deleteConversation,
  inspectTool,
  testTool,
  listAgentDocuments,
  uploadAgentDocument,
  deleteAgentDocument,
} from "./api";

const API = "http://localhost:8000/api";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("api", () => {
  describe("createCanvas", () => {
    it("should successfully create a canvas", async () => {
      const result = await createCanvas("New Canvas");
      expect(result.name).toBe("New Canvas");
    });

    it("should throw error when creation fails", async () => {
      server.use(
        http.post(`${API}/canvases`, () => {
          return new HttpResponse(null, { status: 500 });
        })
      );
      await expect(createCanvas("Fail")).rejects.toThrow("Failed to create canvas");
    });
  });

  describe("listCanvases", () => {
    it("should list canvases", async () => {
      const list = await listCanvases();
      expect(list).toBeInstanceOf(Array);
      expect(list[0].id).toBe("canvas-1");
    });

    it("should throw error when list fails", async () => {
      server.use(
        http.get(`${API}/canvases`, () => {
          return new HttpResponse(null, { status: 500 });
        })
      );
      await expect(listCanvases()).rejects.toThrow("Failed to list canvases");
    });
  });

  describe("getCanvas", () => {
    it("should fetch a single canvas by id", async () => {
      const canvas = await getCanvas("canvas-abc");
      expect(canvas.id).toBe("canvas-abc");
    });

    it("should throw error when get fails", async () => {
      server.use(
        http.get(`${API}/canvases/:id`, () => {
          return new HttpResponse(null, { status: 500 });
        })
      );
      await expect(getCanvas("123")).rejects.toThrow("Failed to get canvas");
    });
  });

  describe("saveCanvas", () => {
    it("should update a canvas", async () => {
      const updated = await saveCanvas("canvas-1", {
        name: "Saved Canvas",
        nodes: { agents: [], tools: [] },
        edges: [],
      });
      expect(updated.name).toBe("Saved Canvas");
    });

    it("should throw error when save fails", async () => {
      server.use(
        http.put(`${API}/canvases/:id`, () => {
          return new HttpResponse(null, { status: 500 });
        })
      );
      await expect(
        saveCanvas("canvas-1", {
          name: "Saved Canvas",
          nodes: { agents: [], tools: [] },
          edges: [],
        })
      ).rejects.toThrow("Failed to save canvas");
    });
  });

  describe("deleteCanvas", () => {
    it("should delete canvas successfully", async () => {
      await expect(deleteCanvas("canvas-1")).resolves.not.toThrow();
    });

    it("should throw error when delete fails", async () => {
      server.use(
        http.delete(`${API}/canvases/:id`, () => {
          return new HttpResponse(null, { status: 500 });
        })
      );
      await expect(deleteCanvas("canvas-1")).rejects.toThrow("Failed to delete canvas");
    });
  });

  describe("exportCanvas", () => {
    it("should export canvas", async () => {
      server.use(
        http.get(`${API}/canvases/:id/export`, ({ params }) => {
          return HttpResponse.json({ id: params.id, name: "Exported" });
        })
      );
      const res = await exportCanvas("canvas-1");
      expect(res.name).toBe("Exported");
    });

    it("should throw error when export fails", async () => {
      server.use(
        http.get(`${API}/canvases/:id/export`, () => {
          return new HttpResponse(null, { status: 500 });
        })
      );
      await expect(exportCanvas("canvas-1")).rejects.toThrow("Failed to export canvas");
    });
  });

  describe("exportCanvasZip", () => {
    it("should export canvas zip", async () => {
      server.use(
        http.get(`${API}/canvases/:id/export-zip`, () => {
          return new HttpResponse("ZIPDATA", {
            status: 200,
            headers: { "Content-Type": "application/zip" },
          });
        })
      );
      const blob = await exportCanvasZip("canvas-1");
      expect(await blob.text()).toBe("ZIPDATA");
    });

    it("should throw error when zip export fails", async () => {
      server.use(
        http.get(`${API}/canvases/:id/export-zip`, () => {
          return new HttpResponse(null, { status: 500 });
        })
      );
      await expect(exportCanvasZip("canvas-1")).rejects.toThrow("Failed to export canvas ZIP");
    });
  });

  describe("importCanvas", () => {
    it("should import canvas", async () => {
      const payload = { name: "Imported Canvas", nodes: { agents: [], tools: [] }, edges: [] };
      const res = await importCanvas(payload);
      expect(res.name).toBe("Imported Canvas");
    });

    it("should throw error when import fails", async () => {
      server.use(
        http.post(`${API}/canvases/import`, () => {
          return new HttpResponse(null, { status: 500 });
        })
      );
      const payload = { name: "Imported Canvas", nodes: { agents: [], tools: [] }, edges: [] };
      await expect(importCanvas(payload)).rejects.toThrow("Failed to import canvas");
    });
  });

  describe("importCanvasZip", () => {
    it("should import canvas zip", async () => {
      server.use(
        http.post(`${API}/canvases/import-zip`, () => {
          return HttpResponse.json({ id: "canvas-zip", name: "Imported Zip Canvas" });
        })
      );
      const file = new File(["zipdata"], "canvas.zip", { type: "application/zip" });
      const res = await importCanvasZip(file);
      expect(res.name).toBe("Imported Zip Canvas");
    });

    it("should throw error when zip import fails", async () => {
      server.use(
        http.post(`${API}/canvases/import-zip`, () => {
          return new HttpResponse(null, { status: 500 });
        }),
        http.post("/api/canvases/import-zip", () => {
          return new HttpResponse(null, { status: 500 });
        })
      );
      const file = new File(["zipdata"], "canvas.zip", { type: "application/zip" });
      await expect(importCanvasZip(file)).rejects.toThrow("Failed to import canvas ZIP");
    });

    it("retries against relative /api when the absolute backend origin fetch fails", async () => {
      const realFetch = global.fetch.bind(globalThis);
      const fetchSpy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;

        if (url === `${API}/canvases/import-zip`) {
          throw new TypeError("Operation failed to fetch");
        }

        if (url === "/api/canvases/import-zip") {
          return new Response(
            JSON.stringify({ id: "canvas-zip", name: "Imported Zip Canvas" }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            }
          );
        }

        return realFetch(input, init);
      });

      vi.stubGlobal("fetch", fetchSpy);

      const file = new File(["zipdata"], "canvas.zip", { type: "application/zip" });
      const res = await importCanvasZip(file);

      expect(res.name).toBe("Imported Zip Canvas");
      expect(fetchSpy).toHaveBeenNthCalledWith(
        1,
        `${API}/canvases/import-zip`,
        expect.objectContaining({ method: "POST" })
      );
      expect(fetchSpy).toHaveBeenNthCalledWith(
        2,
        "/api/canvases/import-zip",
        expect.objectContaining({ method: "POST" })
      );
    });

    it("shows a backend reachability error when both ZIP import endpoints fail", async () => {
      const fetchSpy = vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      });

      vi.stubGlobal("fetch", fetchSpy);

      const file = new File(["zipdata"], "canvas.zip", { type: "application/zip" });

      await expect(importCanvasZip(file)).rejects.toThrow(
        "Failed to import canvas ZIP. Could not reach the backend import endpoint."
      );

      expect(fetchSpy).toHaveBeenCalledTimes(2);
    });
  });

  describe("createConversation", () => {
    it("should create conversation", async () => {
      const res = await createConversation("canvas-1", "My Conv");
      expect(res.name).toBe("My Conv");
      expect(res.canvas_id).toBe("canvas-1");
    });

    it("should throw error when creation fails", async () => {
      server.use(
        http.post(`${API}/canvases/:canvasId/conversations`, () => {
          return new HttpResponse(null, { status: 500 });
        })
      );
      await expect(createConversation("canvas-1", "My Conv")).rejects.toThrow("Failed to create conversation");
    });
  });

  describe("listConversations", () => {
    it("should list conversations", async () => {
      server.use(
        http.get(`${API}/canvases/:canvasId/conversations`, () => {
          return HttpResponse.json([{ id: "conv-1", name: "Conv 1" }]);
        })
      );
      const list = await listConversations("canvas-1");
      expect(list).toHaveLength(1);
      expect(list[0].id).toBe("conv-1");
    });

    it("should throw error when listing fails", async () => {
      server.use(
        http.get(`${API}/canvases/:canvasId/conversations`, () => {
          return new HttpResponse(null, { status: 500 });
        })
      );
      await expect(listConversations("canvas-1")).rejects.toThrow("Failed to list conversations");
    });
  });

  describe("getConversation", () => {
    it("should fetch conversation detail", async () => {
      const conv = await getConversation("canvas-1", "conv-1");
      expect(conv.id).toBe("conv-1");
    });

    it("should throw error when fetch fails", async () => {
      server.use(
        http.get(`${API}/canvases/:canvasId/conversations/:convId`, () => {
          return new HttpResponse(null, { status: 500 });
        })
      );
      await expect(getConversation("canvas-1", "conv-1")).rejects.toThrow("Failed to get conversation");
    });
  });

  describe("deleteConversation", () => {
    it("should delete conversation", async () => {
      await expect(deleteConversation("canvas-1", "conv-1")).resolves.not.toThrow();
    });

    it("should throw error when delete fails", async () => {
      server.use(
        http.delete(`${API}/canvases/:canvasId/conversations/:convId`, () => {
          return new HttpResponse(null, { status: 500 });
        })
      );
      await expect(deleteConversation("canvas-1", "conv-1")).rejects.toThrow("Failed to delete conversation");
    });
  });

  describe("inspectTool", () => {
    it("should inspect tool successfully", async () => {
      const mockResponse = { valid: true, error: null };
      server.use(
        http.post(`${API}/tools/inspect`, () => {
          return HttpResponse.json(mockResponse);
        })
      );
      const res = await inspectTool("print(1)", ["requests"]);
      expect((res as any).valid).toBe(true);
    });

    it("should throw server error with detail when status code is error", async () => {
      server.use(
        http.post(`${API}/tools/inspect`, () => {
          return HttpResponse.json({ detail: "Syntax error in python code" }, { status: 400 });
        })
      );
      await expect(inspectTool("print(1)")).rejects.toThrow("Syntax error in python code");
    });

    it("should fallback to generic error message when json error detail is missing", async () => {
      server.use(
        http.post(`${API}/tools/inspect`, () => {
          return new HttpResponse("Bad request format", { status: 400 });
        })
      );
      await expect(inspectTool("print(1)")).rejects.toThrow("Failed to inspect tool");
    });
  });

  describe("testTool", () => {
    it("should test tool successfully", async () => {
      const mockResponse = { output: "hello", error: null };
      server.use(
        http.post(`${API}/tools/test`, () => {
          return HttpResponse.json(mockResponse);
        })
      );
      const res = await testTool("print(1)", { x: "1" }, ["requests"]);
      expect(res.output).toBe("hello");
    });

    it("should throw server error with detail when testing fails", async () => {
      server.use(
        http.post(`${API}/tools/test`, () => {
          return HttpResponse.json({ detail: "Runtime error" }, { status: 400 });
        })
      );
      await expect(testTool("print(1)", {})).rejects.toThrow("Runtime error");
    });

    it("should fallback to generic error message when test fails with no json body detail", async () => {
      server.use(
        http.post(`${API}/tools/test`, () => {
          return new HttpResponse(null, { status: 400 });
        })
      );
      await expect(testTool("print(1)", {})).rejects.toThrow("Failed to test tool");
    });
  });

  describe("listAgentDocuments", () => {
    it("should list documents successfully", async () => {
      const mockDocs = [{ id: "doc-1", name: "test.txt", created_at: "..." }];
      server.use(
        http.get(`${API}/canvases/:canvasId/agents/:agentId/documents`, () => {
          return HttpResponse.json(mockDocs);
        })
      );
      const res = await listAgentDocuments("canvas-1", "agent-1");
      expect(res).toHaveLength(1);
      expect(res[0].name).toBe("test.txt");
    });

    it("should throw error when list fails", async () => {
      server.use(
        http.get(`${API}/canvases/:canvasId/agents/:agentId/documents`, () => {
          return new HttpResponse(null, { status: 500 });
        })
      );
      await expect(listAgentDocuments("canvas-1", "agent-1")).rejects.toThrow("Failed to list agent documents");
    });
  });

  describe("uploadAgentDocument", () => {
    it("should upload agent document successfully", async () => {
      const mockDoc = { id: "doc-1", name: "test.txt", created_at: "..." };
      server.use(
        http.post(`${API}/canvases/:canvasId/agents/:agentId/documents`, () => {
          return HttpResponse.json(mockDoc);
        })
      );
      const file = new File(["test data"], "test.txt", { type: "text/plain" });
      const res = await uploadAgentDocument("canvas-1", "agent-1", file);
      expect(res.name).toBe("test.txt");
    });

    it("should throw error when upload fails", async () => {
      server.use(
        http.post(`${API}/canvases/:canvasId/agents/:agentId/documents`, () => {
          return new HttpResponse(null, { status: 500 });
        })
      );
      const file = new File(["test data"], "test.txt", { type: "text/plain" });
      await expect(uploadAgentDocument("canvas-1", "agent-1", file)).rejects.toThrow("Failed to upload agent document");
    });
  });

  describe("deleteAgentDocument", () => {
    it("should delete agent document successfully", async () => {
      server.use(
        http.delete(`${API}/canvases/:canvasId/agents/:agentId/documents/:docId`, () => {
          return new HttpResponse(null, { status: 204 });
        })
      );
      await expect(deleteAgentDocument("canvas-1", "agent-1", "doc-1")).resolves.not.toThrow();
    });

    it("should throw error when delete fails", async () => {
      server.use(
        http.delete(`${API}/canvases/:canvasId/agents/:agentId/documents/:docId`, () => {
          return new HttpResponse(null, { status: 500 });
        })
      );
      await expect(deleteAgentDocument("canvas-1", "agent-1", "doc-1")).rejects.toThrow("Failed to delete agent document");
    });
  });
});
