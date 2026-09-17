import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useCanvasStore } from "@/store/canvasStore";
import { AttachmentEditor } from "./AttachmentEditor";
import type { Node } from "@xyflow/react";

const attachmentNode: Node = {
  id: "att-1",
  type: "attachment",
  position: { x: 0, y: 0 },
  data: {
    id: "att-1",
    name: "Sales Data",
    fileType: "csv",
    description: "Q1 export",
  },
};

beforeEach(() => {
  useCanvasStore.getState().reset();
});

describe("AttachmentEditor", () => {
  it("shows placeholder when no attachment node is selected", () => {
    render(<AttachmentEditor />);
    expect(
      screen.getByText("Select an attachment node to edit its properties")
    ).toBeInTheDocument();
  });

  it("renders name, file_type, and description fields for a selected attachment node", () => {
    useCanvasStore.getState().setNodes([attachmentNode]);
    useCanvasStore.getState().selectNode("att-1");
    render(<AttachmentEditor />);

    expect(screen.getByTestId("attachment-name-input")).toHaveValue("Sales Data");
    expect(screen.getByTestId("attachment-file-type-select")).toHaveValue("csv");
    expect(screen.getByTestId("attachment-delivery-method-select")).toHaveValue("inline");
    expect(screen.getByTestId("attachment-description-input")).toHaveValue("Q1 export");
  });

  it("defaults delivery method to inline when the node has no deliveryMethod", () => {
    useCanvasStore.getState().setNodes([attachmentNode]);
    useCanvasStore.getState().selectNode("att-1");
    render(<AttachmentEditor />);

    expect(screen.getByTestId("attachment-delivery-method-select")).toHaveValue("inline");
  });

  it("reflects an existing deliveryMethod from the selected node", () => {
    useCanvasStore.getState().setNodes([
      {
        ...attachmentNode,
        data: { ...attachmentNode.data, deliveryMethod: "file_path" },
      },
    ]);
    useCanvasStore.getState().selectNode("att-1");
    render(<AttachmentEditor />);

    expect(screen.getByTestId("attachment-delivery-method-select")).toHaveValue("file_path");
  });

  it("updates the name in the store when typed", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setNodes([attachmentNode]);
    useCanvasStore.getState().selectNode("att-1");
    render(<AttachmentEditor />);

    await user.clear(screen.getByTestId("attachment-name-input"));
    await user.type(screen.getByTestId("attachment-name-input"), "Renamed");

    const stored = useCanvasStore.getState().nodes.find((n) => n.id === "att-1");
    expect(stored?.data.name).toBe("Renamed");
  });

  it("updates file_type in the store when a curated option is selected", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setNodes([attachmentNode]);
    useCanvasStore.getState().selectNode("att-1");
    render(<AttachmentEditor />);

    await user.selectOptions(screen.getByTestId("attachment-file-type-select"), "python");

    const stored = useCanvasStore.getState().nodes.find((n) => n.id === "att-1");
    expect(stored?.data.fileType).toBe("python");
  });

  it("reveals a freeform text input when 'other' is selected, and stores its value", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setNodes([attachmentNode]);
    useCanvasStore.getState().selectNode("att-1");
    render(<AttachmentEditor />);

    await user.selectOptions(screen.getByTestId("attachment-file-type-select"), "other");
    expect(screen.getByTestId("attachment-file-type-custom-input")).toBeInTheDocument();

    await user.type(
      screen.getByTestId("attachment-file-type-custom-input"),
      "parquet"
    );

    const stored = useCanvasStore.getState().nodes.find((n) => n.id === "att-1");
    expect(stored?.data.fileType).toBe("parquet");
  });

  it("shows the freeform input pre-filled when the node already has a non-curated file_type", () => {
    useCanvasStore.getState().setNodes([
      { ...attachmentNode, data: { ...attachmentNode.data, fileType: "parquet" } },
    ]);
    useCanvasStore.getState().selectNode("att-1");
    render(<AttachmentEditor />);

    expect(screen.getByTestId("attachment-file-type-select")).toHaveValue("other");
    expect(screen.getByTestId("attachment-file-type-custom-input")).toHaveValue("parquet");
  });

  it("updates the description in the store when typed", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setNodes([attachmentNode]);
    useCanvasStore.getState().selectNode("att-1");
    render(<AttachmentEditor />);

    await user.clear(screen.getByTestId("attachment-description-input"));
    await user.type(screen.getByTestId("attachment-description-input"), "New description");

    const stored = useCanvasStore.getState().nodes.find((n) => n.id === "att-1");
    expect(stored?.data.description).toBe("New description");
  });

  it("updates deliveryMethod in the store when the selection changes", () => {
    useCanvasStore.getState().setNodes([attachmentNode]);
    useCanvasStore.getState().selectNode("att-1");
    render(<AttachmentEditor />);

    fireEvent.change(screen.getByTestId("attachment-delivery-method-select"), {
      target: { value: "file_path" },
    });

    const stored = useCanvasStore.getState().nodes.find((n) => n.id === "att-1");
    expect(stored?.data.deliveryMethod).toBe("file_path");
  });
});
