import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ConsumedAttachmentCard } from "./ConsumedAttachmentCard";

describe("ConsumedAttachmentCard", () => {
  it("renders the attachment name, file type, and input label", () => {
    render(
      <ConsumedAttachmentCard
        name="report.csv"
        fileType="csv"
        deliveryMethod="inline"
        attachmentId="attachment-1"
      />
    );

    expect(screen.getByText("report.csv")).toBeInTheDocument();
    expect(screen.getByText(/csv · input/i)).toBeInTheDocument();
    expect(screen.getByTestId("attachment-icon-csv")).toBeInTheDocument();
  });

  it("provides a download link for the uploaded attachment", () => {
    render(
      <ConsumedAttachmentCard
        name="report.csv"
        fileType="csv"
        deliveryMethod="inline"
        attachmentId="attachment-download"
      />
    );

    const downloadLink = screen.getByRole("link", { name: /download/i });
    expect(downloadLink).toHaveAttribute(
      "href",
      "http://localhost:8000/api/attachments/attachment-download"
    );
    expect(downloadLink).toHaveAttribute("download", "report.csv");
  });

  it("shows a path badge for file_path delivery", () => {
    render(
      <ConsumedAttachmentCard
        name="report.csv"
        fileType="csv"
        deliveryMethod="file_path"
        attachmentId="attachment-2"
      />
    );

    expect(screen.getByTestId("attachment-path-badge")).toBeInTheDocument();
    expect(screen.queryByTestId("attachment-thumbnail-image")).not.toBeInTheDocument();
  });

  it("shows both a path badge and thumbnail for dual image delivery", () => {
    render(
      <ConsumedAttachmentCard
        name="plot.png"
        fileType="image"
        deliveryMethod="dual"
        attachmentId="attachment-3"
      />
    );

    expect(screen.getByTestId("attachment-path-badge")).toBeInTheDocument();
    expect(screen.getByTestId("attachment-thumbnail-image")).toHaveAttribute(
      "src",
      "http://localhost:8000/api/attachments/attachment-3"
    );
  });

  it("shows only a thumbnail for inline image delivery", () => {
    render(
      <ConsumedAttachmentCard
        name="plot.png"
        fileType="image"
        deliveryMethod="inline"
        attachmentId="attachment-4"
      />
    );

    expect(screen.getByTestId("attachment-thumbnail-image")).toHaveAttribute(
      "src",
      "http://localhost:8000/api/attachments/attachment-4"
    );
    expect(screen.queryByTestId("attachment-path-badge")).not.toBeInTheDocument();
  });

  it("shows neither badge nor thumbnail for inline non-image delivery", () => {
    render(
      <ConsumedAttachmentCard
        name="report.csv"
        fileType="csv"
        deliveryMethod="inline"
        attachmentId="attachment-5"
      />
    );

    expect(screen.queryByTestId("attachment-path-badge")).not.toBeInTheDocument();
    expect(screen.queryByTestId("attachment-thumbnail-image")).not.toBeInTheDocument();
  });

  it("shows the manifest note for manifest_only delivery", () => {
    render(
      <ConsumedAttachmentCard
        name="archive.bin"
        fileType="binary"
        deliveryMethod="manifest_only"
        attachmentId="attachment-6"
      />
    );

    expect(screen.getByTestId("attachment-manifest-note")).toBeInTheDocument();
  });

  it("shows the original uploaded filename with the attachment node's label in brackets", () => {
    render(
      <ConsumedAttachmentCard
        name="CityName"
        fileType="json"
        deliveryMethod="file_path"
        attachmentId="attachment-7"
        originalFilename="city_name.json"
      />
    );

    expect(screen.getByText("city_name.json")).toBeInTheDocument();
    expect(screen.getByTestId("attachment-node-label")).toHaveTextContent("(CityName)");
    const downloadLink = screen.getByRole("link", { name: /download/i });
    expect(downloadLink).toHaveAttribute("download", "city_name.json");
  });

  it("falls back to the node name with a derived extension when there is no original filename", () => {
    render(
      <ConsumedAttachmentCard
        name="CurrentTemperature"
        fileType="text"
        deliveryMethod="inline"
        attachmentId="attachment-8"
      />
    );

    expect(screen.getByText("CurrentTemperature.txt")).toBeInTheDocument();
    expect(screen.queryByTestId("attachment-node-label")).not.toBeInTheDocument();
  });
});
