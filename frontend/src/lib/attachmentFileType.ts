const FILE_TYPE_BY_EXTENSION: Record<string, string> = {
  csv: "csv",
  json: "json",
  txt: "text",
  md: "text",
  py: "python",
  yaml: "yaml",
  yml: "yaml",
  png: "image",
  jpg: "image",
  jpeg: "image",
  gif: "image",
  bmp: "image",
  webp: "image",
  svg: "image",
  pdf: "pdf",
};

export function guessAttachmentFileType(filename: string): string {
  const lastDotIndex = filename.lastIndexOf(".");
  if (lastDotIndex === -1 || lastDotIndex === filename.length - 1) {
    return "binary";
  }

  const extension = filename.slice(lastDotIndex + 1).toLowerCase();
  return FILE_TYPE_BY_EXTENSION[extension] ?? "binary";
}
