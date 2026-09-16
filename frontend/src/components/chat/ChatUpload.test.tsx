import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { server } from "@/test/mocks/server";
import { FakeWebSocket } from "@/test/mocks/websocket";
import { mockConversation, mockConversationSummary } from "@/test/mocks/handlers";
import { useCanvasStore } from "@/store/canvasStore";
import { useAuthStore } from "@/store/authStore";
import ChatPage from "./ChatPage";

const API = "http://localhost:8000/api";

function renderChatPage(conversationId: string) {
  return render(
    <MemoryRouter initialEntries={[`/chat/${conversationId}`]}>
      <Routes>
        <Route path="/chat/:conversation_id" element={<ChatPage />} />
        <Route path="/chat/empty" element={<ChatPage />} />
      </Routes>
    </MemoryRouter>
  );
}

function primeConversationHandlers() {
  server.use(
    http.get(`${API}/canvases`, () => HttpResponse.json([{ id: "canvas-1", name: "My Canvas" }])),
    http.get(`${API}/canvases/conversations/conv-1`, () =>
      HttpResponse.json(
        mockConversation({
          id: "conv-1",
          canvas_id: "canvas-1",
          name: "Upload Chat",
          messages: [],
        })
      )
    ),
    http.get(`${API}/canvases/canvas-1`, () =>
      HttpResponse.json({
        id: "canvas-1",
        name: "My Canvas",
        nodes: { agents: [], tools: [] },
        edges: [],
      })
    ),
    http.get(`${API}/canvases/canvas-1/conversations`, () =>
      HttpResponse.json([mockConversationSummary({ id: "conv-1", name: "Upload Chat" })])
    )
  );
}

beforeEach(() => {
  useCanvasStore.getState().reset();
  useAuthStore.getState().reset();
  FakeWebSocket.reset();
  vi.stubGlobal("WebSocket", FakeWebSocket);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ChatPage attachment uploads", () => {
  it("shows a staged chip with the guessed type badge after selecting a file", async () => {
    const user = userEvent.setup();
    primeConversationHandlers();
    server.use(
      http.post(`${API}/canvases/conversations/:conversationId/attachments`, () =>
        HttpResponse.json({
          results: [
            {
              filename: "sales.csv",
              success: true,
              attachment_id: "attachment-1",
              node_id: "node-1",
              file_type: "csv",
              error: null,
            },
          ],
        })
      )
    );

    renderChatPage("conv-1");

    await waitFor(() => {
      expect(screen.getByTestId("chat-input")).toBeInTheDocument();
    });

    await user.upload(
      screen.getByTestId("chat-attachment-input"),
      new File(["sales"], "sales.csv", { type: "text/csv" })
    );

    await waitFor(() => {
      expect(screen.getByText("sales.csv")).toBeInTheDocument();
      expect(screen.getByText("CSV")).toBeInTheDocument();
    });
  });

  it("shows a success state after an attachment upload completes", async () => {
    const user = userEvent.setup();
    primeConversationHandlers();
    server.use(
      http.post(`${API}/canvases/conversations/:conversationId/attachments`, () =>
        HttpResponse.json({
          results: [
            {
              filename: "notes.txt",
              success: true,
              attachment_id: "attachment-2",
              node_id: "node-2",
              file_type: "text",
              error: null,
            },
          ],
        })
      )
    );

    renderChatPage("conv-1");

    await waitFor(() => {
      expect(screen.getByTestId("chat-input")).toBeInTheDocument();
    });

    await user.upload(
      screen.getByTestId("chat-attachment-input"),
      new File(["notes"], "notes.txt", { type: "text/plain" })
    );

    await waitFor(() => {
      expect(
        screen.getByLabelText("Attachment notes.txt uploaded")
      ).toBeInTheDocument();
    });
    expect(screen.queryByText(/No input attachment node/)).not.toBeInTheDocument();
  });

  it("shows an inline error when the backend rejects an attachment", async () => {
    const user = userEvent.setup();
    primeConversationHandlers();
    server.use(
      http.post(`${API}/canvases/conversations/:conversationId/attachments`, () =>
        HttpResponse.json({
          results: [
            {
              filename: "payload.bin",
              success: false,
              attachment_id: null,
              node_id: null,
              file_type: "binary",
              error: "No input attachment node on this agent accepts file type 'binary'",
            },
          ],
        })
      )
    );

    renderChatPage("conv-1");

    await waitFor(() => {
      expect(screen.getByTestId("chat-input")).toBeInTheDocument();
    });

    await user.upload(
      screen.getByTestId("chat-attachment-input"),
      new File(["payload"], "payload.bin", { type: "application/octet-stream" })
    );

    await waitFor(() => {
      expect(
        screen.getByText("No input attachment node on this agent accepts file type 'binary'")
      ).toBeInTheDocument();
    });
    expect(screen.getByTestId("chat-input")).toBeInTheDocument();
  });

  it("applies independent per-file results for multiple files dropped together", async () => {
    primeConversationHandlers();
    server.use(
      http.post(`${API}/canvases/conversations/:conversationId/attachments`, async ({ request }) => {
        const formData = await request.formData();
        const files = formData.getAll("files");
        expect(files).toHaveLength(2);
        return HttpResponse.json({
          results: [
            {
              filename: "sales.csv",
              success: true,
              attachment_id: "attachment-1",
              node_id: "node-1",
              file_type: "csv",
              error: null,
            },
            {
              filename: "payload.bin",
              success: false,
              attachment_id: null,
              node_id: null,
              file_type: "binary",
              error: "No input attachment node on this agent accepts file type 'binary'",
            },
          ],
        });
      })
    );

    renderChatPage("conv-1");

    await waitFor(() => {
      expect(screen.getByTestId("chat-attachment-dropzone")).toBeInTheDocument();
    });

    const csvFile = new File(["sales"], "sales.csv", { type: "text/csv" });
    const binFile = new File(["payload"], "payload.bin", {
      type: "application/octet-stream",
    });

    const dropzone = screen.getByTestId("chat-attachment-dropzone");
    await act(async () => {
      fireEvent.dragOver(dropzone, {
        dataTransfer: {
          files: [csvFile, binFile],
          items: [],
          types: ["Files"],
        },
      });
      fireEvent.drop(dropzone, {
        dataTransfer: {
          files: [csvFile, binFile],
          items: [],
          types: ["Files"],
        },
      });
    });

    await waitFor(() => {
      expect(screen.getByText("sales.csv")).toBeInTheDocument();
      expect(screen.getByLabelText("Attachment sales.csv uploaded")).toBeInTheDocument();
      expect(screen.getByText("payload.bin")).toBeInTheDocument();
      expect(
        screen.getByText("No input attachment node on this agent accepts file type 'binary'")
      ).toBeInTheDocument();
    });
  });

  it("removes a rejected attachment chip when requested", async () => {
    const user = userEvent.setup();
    primeConversationHandlers();
    server.use(
      http.post(`${API}/canvases/conversations/:conversationId/attachments`, () =>
        HttpResponse.json({
          results: [
            {
              filename: "payload.bin",
              success: false,
              attachment_id: null,
              node_id: null,
              file_type: "binary",
              error: "No input attachment node on this agent accepts file type 'binary'",
            },
          ],
        })
      )
    );

    renderChatPage("conv-1");

    await waitFor(() => {
      expect(screen.getByTestId("chat-input")).toBeInTheDocument();
    });

    await user.upload(
      screen.getByTestId("chat-attachment-input"),
      new File(["payload"], "payload.bin", { type: "application/octet-stream" })
    );

    await waitFor(() => {
      expect(screen.getByText("payload.bin")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /remove attachment payload\.bin/i }));

    await waitFor(() => {
      expect(screen.queryByText("payload.bin")).not.toBeInTheDocument();
    });
  });

  it("does not offer removal for an already-uploaded attachment (it's already persisted)", async () => {
    const user = userEvent.setup();
    primeConversationHandlers();
    server.use(
      http.post(`${API}/canvases/conversations/:conversationId/attachments`, () =>
        HttpResponse.json({
          results: [
            {
              filename: "notes.txt",
              success: true,
              attachment_id: "attachment-2",
              node_id: "node-2",
              file_type: "text",
              error: null,
            },
          ],
        })
      )
    );

    renderChatPage("conv-1");

    await waitFor(() => {
      expect(screen.getByTestId("chat-input")).toBeInTheDocument();
    });

    await user.upload(
      screen.getByTestId("chat-attachment-input"),
      new File(["notes"], "notes.txt", { type: "text/plain" })
    );

    await waitFor(() => {
      expect(
        screen.getByLabelText("Attachment notes.txt uploaded")
      ).toBeInTheDocument();
    });

    expect(
      screen.queryByRole("button", { name: /remove attachment notes\.txt/i })
    ).not.toBeInTheDocument();
  });

  it("clears uploaded attachment chips after sending the prompt", async () => {
    const user = userEvent.setup();
    primeConversationHandlers();
    server.use(
      http.post(`${API}/canvases/conversations/:conversationId/attachments`, () =>
        HttpResponse.json({
          results: [{
            filename: "notes.txt",
            success: true,
            attachment_id: "attachment-2",
            node_id: "node-2",
            file_type: "text",
            error: null,
          }],
        })
      )
    );

    renderChatPage("conv-1");

    await waitFor(() => expect(screen.getByTestId("chat-input")).toBeInTheDocument());
    await user.upload(
      screen.getByTestId("chat-attachment-input"),
      new File(["notes"], "notes.txt", { type: "text/plain" })
    );
    await waitFor(() => expect(screen.getByText("notes.txt")).toBeInTheDocument());

    await user.type(screen.getByTestId("chat-input"), "Review the attached notes");
    await user.click(screen.getByTestId("send-button"));

    expect(screen.queryByText("notes.txt")).not.toBeInTheDocument();
  });

  it("disables the main composer's attachment picker while a run is active", async () => {
    const user = userEvent.setup();
    primeConversationHandlers();

    renderChatPage("conv-1");

    await waitFor(() => {
      expect(screen.getByTestId("chat-input")).toBeInTheDocument();
    });

    const attachmentButton = screen.getByLabelText("Add attachments");
    expect(attachmentButton).not.toBeDisabled();

    await user.type(screen.getByTestId("chat-input"), "run this workflow");
    await user.click(screen.getByTestId("send-button"));

    await waitFor(() => {
      expect(attachmentButton).toBeDisabled();
    });

    // Dropping a file mid-run must not stage/upload it either, since it would
    // wrongly validate against the entry agent instead of the agent that
    // issued the active HITL prompt.
    const dropzone = screen.getByTestId("chat-attachment-dropzone");
    await act(async () => {
      fireEvent.drop(dropzone, {
        dataTransfer: {
          files: [new File(["sales"], "sales.csv", { type: "text/csv" })],
          items: [],
          types: ["Files"],
        },
      });
    });

    expect(screen.queryByText("sales.csv")).not.toBeInTheDocument();
  });
});
