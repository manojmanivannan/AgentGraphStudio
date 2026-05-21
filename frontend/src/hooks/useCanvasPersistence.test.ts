import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "@/test/mocks/server";
import { useCanvasStore } from "@/store/canvasStore";
import { useCanvasPersistence } from "./useCanvasPersistence";

const store = () => useCanvasStore.getState();

beforeEach(() => {
  vi.useFakeTimers();
  store().reset();
  store().setCanvas("canvas-1", "My Canvas");
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useCanvasPersistence", () => {
  it("does nothing when canvasId is null", async () => {
    store().reset(); // canvasId = null
    const saveSpy = vi.fn();
    server.use(
      http.put("http://localhost:8000/api/canvases/:id", () => {
        saveSpy();
        return HttpResponse.json({});
      })
    );

    renderHook(() => useCanvasPersistence());
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });

    expect(saveSpy).not.toHaveBeenCalled();
  });

  it("debounces save: does not call API before 500ms", async () => {
    const saveSpy = vi.fn();
    server.use(
      http.put("http://localhost:8000/api/canvases/:id", () => {
        saveSpy();
        return HttpResponse.json({});
      })
    );

    renderHook(() => useCanvasPersistence());
    await act(async () => { await vi.advanceTimersByTimeAsync(499); });

    expect(saveSpy).not.toHaveBeenCalled();
  });

  it("calls saveCanvas after 500ms debounce", async () => {
    const saveSpy = vi.fn();
    server.use(
      http.put("http://localhost:8000/api/canvases/:id", async ({ request }) => {
        const body = await request.json();
        saveSpy(body);
        return HttpResponse.json({ id: "canvas-1", name: "My Canvas", nodes: { agents: [], tools: [] }, edges: [], created_at: "", updated_at: "" });
      })
    );

    renderHook(() => useCanvasPersistence());
    await act(async () => { await vi.advanceTimersByTimeAsync(500); });

    expect(saveSpy).toHaveBeenCalledOnce();
    expect(saveSpy).toHaveBeenCalledWith(expect.objectContaining({ name: "My Canvas" }));
  });

  it("skips save when payload has not changed", async () => {
    const saveSpy = vi.fn();
    server.use(
      http.put("http://localhost:8000/api/canvases/:id", () => {
        saveSpy();
        return HttpResponse.json({ id: "canvas-1", name: "My Canvas", nodes: { agents: [], tools: [] }, edges: [], created_at: "", updated_at: "" });
      })
    );

    const { rerender } = renderHook(() => useCanvasPersistence());
    await act(async () => { await vi.advanceTimersByTimeAsync(500); });
    expect(saveSpy).toHaveBeenCalledOnce();

    // Re-render without changing state — payload is identical
    rerender();
    await act(async () => { await vi.advanceTimersByTimeAsync(500); });
    expect(saveSpy).toHaveBeenCalledOnce(); // still only once
  });

  it("saves again after state changes", async () => {
    const saveSpy = vi.fn();
    server.use(
      http.put("http://localhost:8000/api/canvases/:id", () => {
        saveSpy();
        return HttpResponse.json({ id: "canvas-1", name: "My Canvas", nodes: { agents: [], tools: [] }, edges: [], created_at: "", updated_at: "" });
      })
    );

    renderHook(() => useCanvasPersistence());
    await act(async () => { await vi.advanceTimersByTimeAsync(500); });
    expect(saveSpy).toHaveBeenCalledOnce();

    act(() => { store().setName("Renamed"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(500); });
    expect(saveSpy).toHaveBeenCalledTimes(2);
  });

  it("logs error on save failure without crashing", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    server.use(
      http.put("http://localhost:8000/api/canvases/:id", () =>
        new HttpResponse(null, { status: 500 })
      )
    );

    renderHook(() => useCanvasPersistence());
    await act(async () => { await vi.advanceTimersByTimeAsync(500); });

    expect(consoleSpy).toHaveBeenCalledWith(
      "Auto-save failed:",
      expect.any(Error)
    );
    consoleSpy.mockRestore();
  });

  it("retries save on next state change after a failure", async () => {
    const saveSpy = vi.fn();
    // First call fails
    server.use(
      http.put("http://localhost:8000/api/canvases/:id", () =>
        new HttpResponse(null, { status: 500 })
      )
    );

    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    renderHook(() => useCanvasPersistence());
    await act(async () => { await vi.advanceTimersByTimeAsync(500); });

    // Now fix the handler and change state to trigger a new save
    server.use(
      http.put("http://localhost:8000/api/canvases/:id", () => {
        saveSpy();
        return HttpResponse.json({ id: "canvas-1", name: "Retried", nodes: { agents: [], tools: [] }, edges: [], created_at: "", updated_at: "" });
      })
    );

    act(() => { store().setName("Retried"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(500); });
    expect(saveSpy).toHaveBeenCalledOnce();

    consoleSpy.mockRestore();
  });
});
