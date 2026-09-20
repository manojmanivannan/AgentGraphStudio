import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConfirmDialogHost } from "@/components/ui/ConfirmDialogHost";
import { useConfirmStore, confirm } from "@/store/confirmStore";

afterEach(() => {
  cleanup();
  useConfirmStore.setState({ pending: null });
});

describe("ConfirmDialogHost", () => {
  it("renders no dialog when there is no pending confirmation", () => {
    render(<ConfirmDialogHost />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("renders the pending confirmation's title and description", async () => {
    render(<ConfirmDialogHost />);
    void confirm({ title: "Delete document", description: "Are you sure?" });
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Delete document")).toBeInTheDocument();
    expect(screen.getByText("Are you sure?")).toBeInTheDocument();
  });

  it("resolves true and closes when Confirm is clicked", async () => {
    const user = userEvent.setup();
    render(<ConfirmDialogHost />);
    const promise = confirm({ title: "Delete document", confirmLabel: "Delete", danger: true });
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: "Delete" }));
    await expect(promise).resolves.toBe(true);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("resolves false and closes when Cancel is clicked", async () => {
    const user = userEvent.setup();
    render(<ConfirmDialogHost />);
    const promise = confirm({ title: "Delete document" });
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await expect(promise).resolves.toBe(false);
  });

  it("resolves false when dismissed via the close (X) button", async () => {
    const user = userEvent.setup();
    render(<ConfirmDialogHost />);
    const promise = confirm({ title: "Delete document" });
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: "Close" }));
    await expect(promise).resolves.toBe(false);
  });
});
