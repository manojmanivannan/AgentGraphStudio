import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { UnsavedChangesDialogHost } from "@/components/ui/UnsavedChangesDialogHost";
import { useUnsavedChangesPromptStore, promptUnsavedChanges } from "@/store/unsavedChangesPromptStore";

afterEach(() => {
  cleanup();
  useUnsavedChangesPromptStore.setState({ pending: null });
});

describe("UnsavedChangesDialogHost", () => {
  it("renders no dialog when there is no pending prompt", () => {
    render(<UnsavedChangesDialogHost />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("renders the unsaved changes messaging when a prompt is pending", async () => {
    render(<UnsavedChangesDialogHost />);
    void promptUnsavedChanges();
    expect(await screen.findByRole("dialog")).toHaveTextContent("Unsaved changes");
  });

  it("resolves 'save' and closes when Save & continue is clicked", async () => {
    const user = userEvent.setup();
    render(<UnsavedChangesDialogHost />);
    const promise = promptUnsavedChanges();
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: "Save & continue" }));
    await expect(promise).resolves.toBe("save");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("resolves 'discard' and closes when Discard changes is clicked", async () => {
    const user = userEvent.setup();
    render(<UnsavedChangesDialogHost />);
    const promise = promptUnsavedChanges();
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: "Discard changes" }));
    await expect(promise).resolves.toBe("discard");
  });

  it("resolves 'cancel' when Cancel is clicked", async () => {
    const user = userEvent.setup();
    render(<UnsavedChangesDialogHost />);
    const promise = promptUnsavedChanges();
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await expect(promise).resolves.toBe("cancel");
  });

  it("resolves 'cancel' when dismissed via the close (X) button", async () => {
    const user = userEvent.setup();
    render(<UnsavedChangesDialogHost />);
    const promise = promptUnsavedChanges();
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: "Close" }));
    await expect(promise).resolves.toBe("cancel");
  });
});
