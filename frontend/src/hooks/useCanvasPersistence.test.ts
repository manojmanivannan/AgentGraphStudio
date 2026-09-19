import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "@/test/mocks/server";
import { encodeCanvasGraph } from "@/lib/canvasGraphCodec";
import { useCanvasStore } from "@/store/canvasStore";
import {
  saveCanvasNow,
  useSaveShortcut,
  useUnsavedChangesWarning,
} from "./useCanvasPersistence";

const store = () => useCanvasStore.getState();

function buildCanvasResponse(name: string) {
  return {
    id: "canvas-1",
    name,
    nodes: { agents: [], tools: [], attachments: [] },
    edges: [],
    created_at: "",
    updated_at: "",
  };
}

beforeEach(() => {
  vi.useFakeTimers();
  store().reset();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("saveCanvasNow", () => {
  it("does nothing when canvasId is null", async () => {
    const saveSpy = vi.fn();
    server.use(
      http.put("http://localhost:8000/api/canvases/:id", () => {
        saveSpy();
        return HttpResponse.json(buildCanvasResponse("Untitled Canvas"));
      })
    );

    const result = await saveCanvasNow();

    expect(result).toBe(false);
    expect(saveSpy).not.toHaveBeenCalled();
    expect(store().saveStatus).toBe("idle");
  });

  it("saves the encoded payload, clears dirty state, and returns true on success", async () => {
    const nodes = [
      {
        id: "agent-1",
        type: "agent",
        position: { x: 10, y: 20 },
        data: { name: "Planner" },
      },
    ] as any;
    const edges = [{ id: "edge-1", source: "agent-1", target: "tool-1" }] as any;

    store().setCanvas("canvas-1", "My Canvas");
    store().setNodes(nodes);
    store().setEdges(edges);

    const saveSpy = vi.fn();
    server.use(
      http.put("http://localhost:8000/api/canvases/:id", async ({ request, params }) => {
        saveSpy(params.id, await request.json());
        return HttpResponse.json(buildCanvasResponse("My Canvas"));
      })
    );

    const result = await saveCanvasNow();
    const expectedPayload = encodeCanvasGraph({
      canvasName: "My Canvas",
      nodes,
      edges,
    });

    expect(result).toBe(true);
    expect(saveSpy).toHaveBeenCalledOnce();
    expect(saveSpy).toHaveBeenCalledWith("canvas-1", expectedPayload);
    expect(store().saveStatus).toBe("saved");
    expect(store().isDirty).toBe(false);
  });

  it("sets error status, logs, and returns false on failure without throwing", async () => {
    store().setCanvas("canvas-1", "Broken Canvas");
    store().setName("Broken Canvas");

    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    server.use(
      http.put("http://localhost:8000/api/canvases/:id", () =>
        new HttpResponse(null, { status: 500 })
      )
    );

    await expect(saveCanvasNow()).resolves.toBe(false);

    expect(store().saveStatus).toBe("error");
    expect(store().isDirty).toBe(true);
    expect(consoleSpy).toHaveBeenCalledWith("Save failed:", expect.any(Error));
  });

  it("resets save status to idle 3000ms after a successful save", async () => {
    store().setCanvas("canvas-1", "My Canvas");
    store().setName("Renamed Canvas");

    server.use(
      http.put("http://localhost:8000/api/canvases/:id", () =>
        HttpResponse.json(buildCanvasResponse("Renamed Canvas"))
      )
    );

    await saveCanvasNow();
    expect(store().saveStatus).toBe("saved");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });

    expect(store().saveStatus).toBe("idle");
  });

  it("resets save status to idle 3000ms after a failed save", async () => {
    store().setCanvas("canvas-1", "My Canvas");
    store().setName("Unsaved Canvas");

    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    server.use(
      http.put("http://localhost:8000/api/canvases/:id", () =>
        new HttpResponse(null, { status: 500 })
      )
    );

    await saveCanvasNow();
    expect(store().saveStatus).toBe("error");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });

    expect(store().saveStatus).toBe("idle");
    expect(consoleSpy).toHaveBeenCalledOnce();
  });
});

describe("useUnsavedChangesWarning", () => {
  it("prevents unload when the canvas is dirty", () => {
    renderHook(() => useUnsavedChangesWarning());
    store().setIsDirty(true);

    const event = new Event("beforeunload", { cancelable: true });
    const dispatchResult = window.dispatchEvent(event);

    expect(dispatchResult).toBe(false);
    expect(event.defaultPrevented).toBe(true);
  });

  it("allows unload when the canvas is clean", () => {
    renderHook(() => useUnsavedChangesWarning());
    store().setIsDirty(false);

    const event = new Event("beforeunload", { cancelable: true });
    const dispatchResult = window.dispatchEvent(event);

    expect(dispatchResult).toBe(true);
    expect(event.defaultPrevented).toBe(false);
  });
});

describe("useSaveShortcut", () => {
  it("triggers a save attempt on Ctrl+S and prevents the browser default", async () => {
    store().setCanvas("canvas-1", "Shortcut Canvas");
    store().setName("Shortcut Canvas");

    const saveSpy = vi.fn();
    let resolveRequest: (() => void) | undefined;
    const requestSeen = new Promise<void>((resolve) => {
      resolveRequest = resolve;
    });

    server.use(
      http.put("http://localhost:8000/api/canvases/:id", async ({ request }) => {
        saveSpy(await request.json());
        resolveRequest?.();
        return HttpResponse.json(buildCanvasResponse("Shortcut Canvas"));
      })
    );

    renderHook(() => useSaveShortcut());

    const event = new KeyboardEvent("keydown", {
      key: "s",
      ctrlKey: true,
      cancelable: true,
    });

    act(() => {
      window.dispatchEvent(event);
    });

    await act(async () => {
      await requestSeen;
    });

    expect(event.defaultPrevented).toBe(true);
    expect(saveSpy).toHaveBeenCalledOnce();
    expect(store().saveStatus).toBe("saved");
  });
});
