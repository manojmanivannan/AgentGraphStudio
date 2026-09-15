import { beforeEach, describe, expect, it } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import { useCanvasStore } from "@/store/canvasStore";
import { PropertiesOverlay } from "./PropertiesOverlay";

// OverlayPanel only plays its "open" transition (and mounts children) on a
// closed->open state change detected after mount, so tests must select a
// node *after* the initial render rather than starting pre-selected.

beforeEach(() => {
  useCanvasStore.getState().reset();
});

describe("PropertiesOverlay", () => {
  it("renders nothing when no node is selected", () => {
    render(<PropertiesOverlay />);
    expect(screen.queryByTestId("properties-close")).not.toBeInTheDocument();
  });

  it("renders the AgentEditor and an agent name for a selected agent node", async () => {
    render(<PropertiesOverlay />);

    act(() => {
      useCanvasStore.getState().setNodes([
        {
          id: "agent-1",
          type: "agent",
          position: { x: 0, y: 0 },
          data: { id: "agent-1", name: "My Agent", agentType: "worker" },
        } as any,
      ]);
      useCanvasStore.getState().selectNode("agent-1");
    });

    await waitFor(() =>
      expect(document.querySelector('input[value="My Agent"]')).toBeInTheDocument()
    );
  });

  it("renders the ToolEditor for a selected tool node", async () => {
    render(<PropertiesOverlay />);

    act(() => {
      useCanvasStore.getState().setNodes([
        {
          id: "tool-1",
          type: "tool",
          position: { x: 0, y: 0 },
          data: { id: "tool-1", name: "My Tool", code: "" },
        } as any,
      ]);
      useCanvasStore.getState().selectNode("tool-1");
    });

    await waitFor(() =>
      expect(screen.getAllByText("My Tool").length).toBeGreaterThan(0)
    );
  });

  it("renders the AttachmentEditor for a selected attachment node", async () => {
    render(<PropertiesOverlay />);

    act(() => {
      useCanvasStore.getState().setNodes([
        {
          id: "attachment-1",
          type: "attachment",
          position: { x: 0, y: 0 },
          data: { id: "attachment-1", name: "My File", fileType: "csv", description: "" },
        } as any,
      ]);
      useCanvasStore.getState().selectNode("attachment-1");
    });

    await waitFor(() =>
      expect(document.querySelector('input[value="My File"]')).toBeInTheDocument()
    );
    expect(screen.getByRole("combobox")).toBeInTheDocument();
  });

  it("closes the overlay when the close button is clicked", async () => {
    render(<PropertiesOverlay />);

    act(() => {
      useCanvasStore.getState().setNodes([
        {
          id: "tool-1",
          type: "tool",
          position: { x: 0, y: 0 },
          data: { id: "tool-1", name: "My Tool", code: "" },
        } as any,
      ]);
      useCanvasStore.getState().selectNode("tool-1");
    });

    const closeBtn = await waitFor(() => screen.getByTestId("properties-close"));
    act(() => {
      closeBtn.click();
    });

    expect(useCanvasStore.getState().selectedNodeId).toBeNull();
  });
});
