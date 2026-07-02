import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ChatSidebar } from "./ChatSidebar";

const mockConversations = [
  { id: "1", name: "Chat 1", canvas_id: "canvas-1", created_at: "2024-01-01", updated_at: "2024-01-01", status: "active" as const },
];

const defaultProps = {
  sidebarCollapsed: false,
  setSidebarCollapsed: vi.fn(),
  theme: "dark" as const,
  canvasId: "canvas-1",
  conversation_id: "1",
  conversations: mockConversations,
  handleNewConversation: vi.fn(),
  handleExportConversation: vi.fn(),
  setDeleteConfirmId: vi.fn(),
  handleImportClick: vi.fn(),
  fileInputRef: { current: null },
  handleFileChange: vi.fn(),
};

describe("ChatSidebar", () => {
  it("renders new chat button", () => {
    render(
      <MemoryRouter>
        <ChatSidebar {...defaultProps} />
      </MemoryRouter>
    );
    expect(screen.getByTestId("new-chat-btn")).toBeInTheDocument();
  });

  it("calls setSidebarCollapsed when collapse button is clicked", () => {
    const setCollapsed = vi.fn();
    render(
      <MemoryRouter>
        <ChatSidebar {...defaultProps} setSidebarCollapsed={setCollapsed} />
      </MemoryRouter>
    );
    fireEvent.click(screen.getByTestId("collapse-sidebar"));
    expect(setCollapsed).toHaveBeenCalledWith(true);
  });

  it("renders conversations list", () => {
    render(
      <MemoryRouter>
        <ChatSidebar {...defaultProps} />
      </MemoryRouter>
    );
    expect(screen.getByText("Chat 1")).toBeInTheDocument();
  });
});
