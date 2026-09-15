import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProducedAttachmentCard } from "./ProducedAttachmentCard";

describe("ProducedAttachmentCard", () => {
  it("renders the attachment name, image icon, and download link", () => {
    render(
      <ProducedAttachmentCard
        name="plot.png"
        fileType="image"
        attachmentId="attachment-123"
      />
    );

    expect(screen.getByText("plot.png")).toBeInTheDocument();
    expect(screen.getByTestId("attachment-icon-image")).toBeInTheDocument();

    const downloadLink = screen.getByRole("link", { name: /download/i });
    expect(downloadLink).toHaveAttribute(
      "href",
      "http://localhost:8000/api/attachments/attachment-123"
    );
    expect(downloadLink).toHaveAttribute("download");
  });

  it("uses a JSON icon for json attachments", () => {
    render(
      <ProducedAttachmentCard
        name="report.json"
        fileType="json"
        attachmentId="attachment-json"
      />
    );

    expect(screen.getByTestId("attachment-icon-json")).toBeInTheDocument();
  });
});
