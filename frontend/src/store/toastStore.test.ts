import { describe, it, expect, beforeEach } from "vitest";
import { useToastStore, toast } from "@/store/toastStore";

beforeEach(() => {
  useToastStore.setState({ toasts: [] });
});

describe("toastStore", () => {
  it("starts with no toasts", () => {
    expect(useToastStore.getState().toasts).toEqual([]);
  });

  it("show() appends a toast with the given message and variant", () => {
    useToastStore.getState().show("Saved", "success");
    const [entry] = useToastStore.getState().toasts;
    expect(entry).toMatchObject({ message: "Saved", variant: "success" });
  });

  it("show() defaults to the info variant", () => {
    useToastStore.getState().show("Heads up");
    expect(useToastStore.getState().toasts[0].variant).toBe("info");
  });

  it("assigns each toast a unique id", () => {
    useToastStore.getState().show("first");
    useToastStore.getState().show("second");
    const [a, b] = useToastStore.getState().toasts;
    expect(a.id).not.toBe(b.id);
  });

  it("dismiss() removes the toast with the matching id", () => {
    const id = useToastStore.getState().show("bye");
    useToastStore.getState().dismiss(id);
    expect(useToastStore.getState().toasts).toEqual([]);
  });

  describe("toast API", () => {
    it("toast.error() pushes an error-variant toast", () => {
      toast.error("Failed to upload document");
      expect(useToastStore.getState().toasts[0]).toMatchObject({
        message: "Failed to upload document",
        variant: "error",
      });
    });

    it("toast.success() pushes a success-variant toast", () => {
      toast.success("Done");
      expect(useToastStore.getState().toasts[0].variant).toBe("success");
    });

    it("toast.info() pushes an info-variant toast", () => {
      toast.info("FYI");
      expect(useToastStore.getState().toasts[0].variant).toBe("info");
    });
  });
});
