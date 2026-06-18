import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SidebarRail } from "./SidebarRail";
import { useCanvasStore } from "@/store/canvasStore";
import { MemoryRouter } from "react-router-dom";

vi.mock("@/lib/api", () => ({
  exportCanvasZip: vi.fn(),
  importCanvas: vi.fn(),
  importCanvasZip: vi.fn(),
  listConversations: vi.fn().mockResolvedValue([]),
  createConversation: vi.fn().mockResolvedValue({ id: "new-conv" }),
}));

describe("SidebarRail", () => {
  beforeEach(() => {
    useCanvasStore.getState().reset();
  });

  const renderSidebar = () => {
    return render(
      <MemoryRouter>
        <SidebarRail />
      </MemoryRouter>
    );
  };

  it("renders basic layout and elements", () => {
    useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");
    renderSidebar();

    expect(screen.getByText("AgentGraph Studio")).toBeInTheDocument();
    expect(screen.getByText("Home")).toBeInTheDocument();
    expect(screen.getByText("Visual Canvas")).toBeInTheDocument();
    expect(screen.getByText("Agent Chat")).toBeInTheDocument();
    expect(screen.getByText("Observability")).toBeInTheDocument();
  });

  it("adds worker and router agents on button clicks", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");
    renderSidebar();

    const addWorkerBtn = screen.getByTestId("add-agent-worker");
    const addRouterBtn = screen.getByTestId("add-agent-router");

    await user.click(addWorkerBtn);
    await user.click(addRouterBtn);

    const nodes = useCanvasStore.getState().nodes;
    expect(nodes).toHaveLength(2);
    expect(nodes[0].data.agentType).toBe("worker");
    expect(nodes[1].data.agentType).toBe("router");
  });

  it("adds a custom tool on button click", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");
    renderSidebar();

    const addToolBtn = screen.getByTestId("add-tool-button");
    await user.click(addToolBtn);

    const nodes = useCanvasStore.getState().nodes;
    expect(nodes).toHaveLength(1);
    expect(nodes[0].type).toBe("tool");
  });

  it("opens clear popover and clears the canvas", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");
    useCanvasStore.getState().setNodes([{ id: "n1", type: "agent", position: { x: 0, y: 0 }, data: {} as any }]);
    
    renderSidebar();

    const clearBtn = screen.getByTestId("clear-canvas-button");
    await user.click(clearBtn);

    // Verify popover is open
    expect(screen.getByText("Clear all nodes and edges?")).toBeInTheDocument();

    const confirmClearBtn = screen.getByRole("button", { name: "Clear" });
    await user.click(confirmClearBtn);

    expect(useCanvasStore.getState().nodes).toHaveLength(0);
  });

  it("closes clear popover on clicking cancel", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");
    renderSidebar();

    const clearBtn = screen.getByTestId("clear-canvas-button");
    await user.click(clearBtn);

    const cancelBtn = screen.getByRole("button", { name: "Cancel" });
    await user.click(cancelBtn);

    expect(screen.queryByText("Clear all nodes and edges?")).not.toBeInTheDocument();
  });

  it("closes clear popover on pressing Escape key", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");
    renderSidebar();

    const clearBtn = screen.getByTestId("clear-canvas-button");
    await user.click(clearBtn);
    expect(screen.getByText("Clear all nodes and edges?")).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape", code: "Escape" });
    expect(screen.queryByText("Clear all nodes and edges?")).not.toBeInTheDocument();
  });

  it("closes clear popover on clicking outside", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");
    renderSidebar();

    const clearBtn = screen.getByTestId("clear-canvas-button");
    await user.click(clearBtn);
    expect(screen.getByText("Clear all nodes and edges?")).toBeInTheDocument();

    fireEvent.mouseDown(document.body);
    expect(screen.queryByText("Clear all nodes and edges?")).not.toBeInTheDocument();
  });

  it("calls exportCanvasZip when exporting a canvas", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");
    
    window.URL.createObjectURL = vi.fn().mockReturnValue("blob:mock-url");
    window.URL.revokeObjectURL = vi.fn();
    
    const { exportCanvasZip } = await import("@/lib/api");
    vi.mocked(exportCanvasZip).mockResolvedValue(new Blob(["dummy"], { type: "application/zip" }));

    renderSidebar();

    const exportBtn = screen.getByTestId("export-button");
    await user.click(exportBtn);

    expect(exportCanvasZip).toHaveBeenCalledWith("canvas-1");
  });

  it("triggers file input click on import button click", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");
    
    renderSidebar();

    const importBtn = screen.getByTestId("import-button");
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    const clickSpy = vi.spyOn(fileInput, "click");

    await user.click(importBtn);

    expect(clickSpy).toHaveBeenCalled();
  });

  it("navigates to chat when chat button is clicked", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");
    
    const { listConversations } = await import("@/lib/api");
    vi.mocked(listConversations).mockResolvedValue([{ id: "conv-1", canvas_id: "canvas-1", name: "Chat" } as any]);

    renderSidebar();

    const chatBtn = screen.getByTestId("chat-toggle");
    await user.click(chatBtn);

    await waitFor(() => {
      expect(listConversations).toHaveBeenCalledWith("canvas-1");
    });
  });

  it("collapses and expands the sidebar on clicking the app logo/icon", async () => {
    const user = userEvent.setup();
    act(() => {
      useCanvasStore.getState().setCanvas("canvas-1", "Test Canvas");
      useCanvasStore.setState({ sidebarCollapsed: false });
    });
    renderSidebar();

    const logoBtn = screen.getByTestId("collapse-sidebar");
    await user.click(logoBtn);
    expect(useCanvasStore.getState().sidebarCollapsed).toBe(true);
  });
});
