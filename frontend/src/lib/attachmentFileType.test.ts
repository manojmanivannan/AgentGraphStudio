import { describe, expect, it } from "vitest";
import { guessAttachmentFileType } from "./attachmentFileType";

describe("guessAttachmentFileType", () => {
  it.each([
    ["sales.csv", "csv"],
    ["payload.json", "json"],
    ["notes.txt", "text"],
    ["README.md", "text"],
    ["script.py", "python"],
    ["config.yaml", "yaml"],
    ["config.yml", "yaml"],
    ["diagram.png", "image"],
    ["photo.jpg", "image"],
    ["photo.jpeg", "image"],
    ["animation.gif", "image"],
    ["bitmap.bmp", "image"],
    ["cover.webp", "image"],
    ["icon.svg", "image"],
    ["paper.pdf", "pdf"],
  ])("maps %s to %s", (filename, expected) => {
    expect(guessAttachmentFileType(filename)).toBe(expected);
  });

  it("matches extensions case-insensitively", () => {
    expect(guessAttachmentFileType("REPORT.CSV")).toBe("csv");
    expect(guessAttachmentFileType("Guide.Md")).toBe("text");
    expect(guessAttachmentFileType("Photo.JPEG")).toBe("image");
  });

  it("falls back to binary for files without an extension", () => {
    expect(guessAttachmentFileType("LICENSE")).toBe("binary");
  });

  it("falls back to binary for unknown extensions", () => {
    expect(guessAttachmentFileType("archive.parquet")).toBe("binary");
  });
});
