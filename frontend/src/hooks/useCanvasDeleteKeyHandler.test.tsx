import { beforeEach, describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import { useCanvasStore } from "@/store/canvasStore";
import { useCanvasDeleteKeyHandler } from "./useCanvasDeleteKeyHandler";

const deleteSelectedNodesWithConfirmMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/nodeDeletion", () => ({
  deleteSelectedNodesWithConfirm: deleteSelectedNodesWithConfirmMock,
}));

function TestHost() {
  useCanvasDeleteKeyHandler();
  return (
    <div>
      <input data-testid="text-input" defaultValue="" />
    </div>
  );
}

function fireKeydown(target: EventTarget, key: string) {
  const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true });
  target.dispatchEvent(event);
  return event;
}

beforeEach(() => {
  useCanvasStore.getState().reset();
  deleteSelectedNodesWithConfirmMock.mockReset();
  deleteSelectedNodesWithConfirmMock.mockResolvedValue(true);
});

describe("useCanvasDeleteKeyHandler", () => {
  it("triggers deletion on Backspace when a node is selected", () => {
    useCanvasStore.getState().setNodes([
      { id: "n1", type: "agent", position: { x: 0, y: 0 }, data: { name: "Agent 1" }, selected: true } as any,
    ]);
    render(<TestHost />);

    fireKeydown(window, "Backspace");

    expect(deleteSelectedNodesWithConfirmMock).toHaveBeenCalledTimes(1);
  });

  it("triggers deletion on Delete when a node is selected", () => {
    useCanvasStore.getState().setNodes([
      { id: "n1", type: "agent", position: { x: 0, y: 0 }, data: { name: "Agent 1" }, selected: true } as any,
    ]);
    render(<TestHost />);

    fireKeydown(window, "Delete");

    expect(deleteSelectedNodesWithConfirmMock).toHaveBeenCalledTimes(1);
  });

  it("does not trigger deletion when no node is selected", () => {
    useCanvasStore.getState().setNodes([
      { id: "n1", type: "agent", position: { x: 0, y: 0 }, data: { name: "Agent 1" }, selected: false } as any,
    ]);
    render(<TestHost />);

    fireKeydown(window, "Backspace");

    expect(deleteSelectedNodesWithConfirmMock).not.toHaveBeenCalled();
  });

  it("ignores Backspace while focus is inside a text input", () => {
    useCanvasStore.getState().setNodes([
      { id: "n1", type: "agent", position: { x: 0, y: 0 }, data: { name: "Agent 1" }, selected: true } as any,
    ]);
    const { getByTestId } = render(<TestHost />);

    fireKeydown(getByTestId("text-input"), "Backspace");

    expect(deleteSelectedNodesWithConfirmMock).not.toHaveBeenCalled();
  });

  it("ignores unrelated keys", () => {
    useCanvasStore.getState().setNodes([
      { id: "n1", type: "agent", position: { x: 0, y: 0 }, data: { name: "Agent 1" }, selected: true } as any,
    ]);
    render(<TestHost />);

    fireKeydown(window, "a");

    expect(deleteSelectedNodesWithConfirmMock).not.toHaveBeenCalled();
  });
});
