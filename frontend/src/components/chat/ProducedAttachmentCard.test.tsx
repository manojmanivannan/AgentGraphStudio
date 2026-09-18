import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProducedAttachmentCard } from "./ProducedAttachmentCard";

describe("ProducedAttachmentCard", () => {
  it("renders an image thumbnail preview for image attachments", () => {
    render(
      <ProducedAttachmentCard
        name="plot.png"
        fileType="image"
        attachmentId="attachment-123"
      />
    );

    expect(screen.getByText("plot.png")).toBeInTheDocument();
    expect(screen.getByTestId("attachment-icon-image")).toBeInTheDocument();
    expect(screen.getByTestId("attachment-thumbnail-image")).toHaveAttribute(
      "src",
      "http://localhost:8000/api/attachments/attachment-123"
    );
    expect(screen.getByTestId("attachment-thumbnail-image")).toHaveAttribute(
      "alt",
      "plot.png"
    );

    const downloadLink = screen.getByRole("link", { name: /download/i });
    expect(downloadLink).toHaveAttribute(
      "href",
      "http://localhost:8000/api/attachments/attachment-123"
    );
    expect(downloadLink).toHaveAttribute("download");
  });

  it("does not render an image thumbnail for non-image attachments", () => {
    render(
      <ProducedAttachmentCard
        name="report.csv"
        fileType="csv"
        attachmentId="attachment-csv"
      />
    );

    expect(screen.getByText("report.csv")).toBeInTheDocument();
    expect(screen.getByTestId("attachment-icon-csv")).toBeInTheDocument();
    expect(screen.queryByTestId("attachment-thumbnail-image")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /download/i })).toHaveAttribute(
      "href",
      "http://localhost:8000/api/attachments/attachment-csv"
    );
  });

  it("appends a file_type-derived extension when the name doesn't already carry one", () => {
    render(
      <ProducedAttachmentCard
        name="CurrentTemperature"
        fileType="text"
        attachmentId="attachment-temp"
      />
    );

    expect(screen.getByText("CurrentTemperature.txt")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /download/i })).toHaveAttribute(
      "download",
      "CurrentTemperature.txt"
    );
  });
});
