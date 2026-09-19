import { beforeEach, describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import { useCanvasUndoRedoShortcuts } from "./useCanvasUndoRedoShortcuts";

const undoMock = vi.hoisted(() => vi.fn());
const redoMock = vi.hoisted(() => vi.fn());

vi.mock("@/store/canvasHistoryStore", () => ({
  useCanvasHistoryStore: {
    getState: () => ({
      undo: undoMock,
      redo: redoMock,
    }),
  },
}));

function TestHost() {
  useCanvasUndoRedoShortcuts();
  return (
    <div>
      <input data-testid="text-input" defaultValue="" />
    </div>
  );
}

function fireKeydown(target: EventTarget, key: string, init?: KeyboardEventInit) {
  const event = new KeyboardEvent("keydown", {
    key,
    bubbles: true,
    cancelable: true,
    ...init,
  });
  target.dispatchEvent(event);
  return event;
}

beforeEach(() => {
  undoMock.mockReset();
  redoMock.mockReset();
});

describe("useCanvasUndoRedoShortcuts", () => {
  it("triggers undo on Ctrl+Z", () => {
    render(<TestHost />);

    fireKeydown(window, "z", { ctrlKey: true });

    expect(undoMock).toHaveBeenCalledTimes(1);
    expect(redoMock).not.toHaveBeenCalled();
  });

  it("triggers undo on Cmd+Z", () => {
    render(<TestHost />);

    fireKeydown(window, "z", { metaKey: true });

    expect(undoMock).toHaveBeenCalledTimes(1);
    expect(redoMock).not.toHaveBeenCalled();
  });

  it("triggers redo on Ctrl+Shift+Z", () => {
    render(<TestHost />);

    fireKeydown(window, "z", { ctrlKey: true, shiftKey: true });

    expect(redoMock).toHaveBeenCalledTimes(1);
    expect(undoMock).not.toHaveBeenCalled();
  });

  it("triggers redo on Ctrl+Y", () => {
    render(<TestHost />);

    fireKeydown(window, "y", { ctrlKey: true });

    expect(redoMock).toHaveBeenCalledTimes(1);
    expect(undoMock).not.toHaveBeenCalled();
  });

  it("ignores plain z without a modifier", () => {
    render(<TestHost />);

    fireKeydown(window, "z");

    expect(undoMock).not.toHaveBeenCalled();
    expect(redoMock).not.toHaveBeenCalled();
  });

  it("ignores Ctrl+Z while focus is inside a text input", () => {
    const { getByTestId } = render(<TestHost />);

    fireKeydown(getByTestId("text-input"), "z", { ctrlKey: true });

    expect(undoMock).not.toHaveBeenCalled();
    expect(redoMock).not.toHaveBeenCalled();
  });

  it("ignores unrelated keys", () => {
    render(<TestHost />);

    fireKeydown(window, "a", { ctrlKey: true });

    expect(undoMock).not.toHaveBeenCalled();
    expect(redoMock).not.toHaveBeenCalled();
  });
});
