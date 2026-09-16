import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  interceptAttachmentUpload,
  jsonAttachmentUploadResponse,
} from "@/test/mocks/attachmentUpload";
import { HitlAttachmentUpload } from "./HitlAttachmentUpload";

const API = "http://localhost:8000/api";

describe("HitlAttachmentUpload", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("uploads a selected file against the prompting agent and shows success", async () => {
    const user = userEvent.setup();

    interceptAttachmentUpload((url, formData) => {
      expect(url).toBe(`${API}/canvases/conversations/conv-1/attachments`);
      const files = formData.getAll("files");
      expect(files).toHaveLength(1);
      expect((files[0] as File).name).toBe("sales.csv");
      expect(formData.get("agent_id")).toBe("agent-node-1");
      return jsonAttachmentUploadResponse([
        {
          filename: "sales.csv",
          success: true,
          attachment_id: "attachment-1",
          node_id: "node-1",
          file_type: "csv",
          error: null,
        },
      ]);
    });

    render(
      <HitlAttachmentUpload conversationId="conv-1" agentNodeId="agent-node-1" />
    );

    await user.upload(
      screen.getByTestId("hitl-attachment-input"),
      new File(["sales"], "sales.csv", { type: "text/csv" })
    );

    await waitFor(() => {
      expect(screen.getByText("Uploaded sales.csv")).toBeInTheDocument();
    });
  });

  it("shows the backend error inline when the upload is rejected", async () => {
    const user = userEvent.setup();

    interceptAttachmentUpload((url, formData) => {
      expect(formData.get("agent_id")).toBeNull();
      return jsonAttachmentUploadResponse([
        {
          filename: "malware.exe",
          success: false,
          attachment_id: null,
          node_id: null,
          file_type: "binary",
          error: "No input attachment node on this agent accepts file type 'binary'",
        },
      ]);
    });

    render(<HitlAttachmentUpload conversationId="conv-1" />);

    await user.upload(
      screen.getByTestId("hitl-attachment-input"),
      new File(["exe"], "malware.exe", { type: "application/octet-stream" })
    );

    await waitFor(() => {
      expect(
        screen.getByText("No input attachment node on this agent accepts file type 'binary'")
      ).toBeInTheDocument();
    });
  });
});
