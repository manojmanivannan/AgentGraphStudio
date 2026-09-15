import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/test/mocks/server";
import { HitlAttachmentUpload } from "./HitlAttachmentUpload";

const API = "http://localhost:8000/api";

describe("HitlAttachmentUpload", () => {
  it("uploads a selected file against the prompting agent and shows success", async () => {
    const user = userEvent.setup();

    server.use(
      http.post(`${API}/canvases/conversations/:conversationId/attachments`, async ({ params, request }) => {
        expect(params.conversationId).toBe("conv-1");
        const formData = await request.formData();
        const files = formData.getAll("files");
        expect(files).toHaveLength(1);
        expect(formData.get("agent_id")).toBe("agent-node-1");
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
          ],
        });
      })
    );

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

    server.use(
      http.post(`${API}/canvases/conversations/:conversationId/attachments`, async ({ request }) => {
        const formData = await request.formData();
        expect(formData.get("agent_id")).toBeNull();
        return HttpResponse.json({
          results: [
            {
              filename: "malware.exe",
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
