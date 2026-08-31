import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { Modal } from "@/components/ui/Modal";

function ClickThrough({ onAction }: { onAction?: () => void }) {
  return (
    <div>
      <button onClick={onAction}>first</button>
      <button>second</button>
      <input data-testid="text-input" />
    </div>
  );
}

function NestedExample({ onClose }: { onClose: () => void }) {
  return (
    <Modal open title="Nested" onClose={onClose}>
      <button>nested button</button>
    </Modal>
  );
}

/** Host that renders an open modal plus an optional nested child modal. */
function ModalHost(props: { nested?: boolean }) {
  const [open, setOpen] = useState(true);
  const [nestedOpen, setNestedOpen] = useState(props.nested ?? false);
  return (
    <div>
      <button onClick={() => setOpen(true)}>reopen</button>
      <Modal open={open} title="Settings" onClose={() => setOpen(false)}>
        <ClickThrough onAction={() => setNestedOpen(true)} />
        {nestedOpen && <NestedExample onClose={() => setNestedOpen(false)} />}
      </Modal>
    </div>
  );
}

afterEach(() => {
  cleanup();
});

describe("Modal", () => {
  it("renders nothing when closed", () => {
    render(
      <Modal open={false} title="Settings" onClose={() => {}}>
        <p>body</p>
      </Modal>
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByText("body")).not.toBeInTheDocument();
  });

  it("renders a labelled dialog with its content via a portal", () => {
    render(
      <Modal open title="Settings" onClose={() => {}}>
        <p>body</p>
      </Modal>
    );
    const dialog = screen.getByRole("dialog", { name: "Settings" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByText("body")).toBeInTheDocument();
  });

  it("calls onClose when Escape is pressed on the topmost modal", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <Modal open title="Settings" onClose={onClose}>
        <p>body</p>
      </Modal>
    );
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does not swallow Escape when closed", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <Modal open={false} title="Settings" onClose={onClose}>
        <p>body</p>
      </Modal>
    );
    await user.keyboard("{Escape}");
    expect(onClose).not.toHaveBeenCalled();
  });

  it("topmost nested modal consumes Escape; the outer modal stays open", async () => {
    const user = userEvent.setup();
    render(<ModalHost nested />);

    await user.keyboard("{Escape}");
    // Nested closes...
    expect(screen.queryByText("nested button")).not.toBeInTheDocument();
    // ...outer stays open.
    expect(screen.getByRole("dialog", { name: "Settings" })).toBeInTheDocument();

    // Second Escape now reaches the outer modal.
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Settings" })).not.toBeInTheDocument();
  });

  it("calls onClose on backdrop mousedown but not on clicks inside the panel", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <Modal open title="Settings" onClose={onClose}>
        <button>inside</button>
      </Modal>
    );
    await user.click(screen.getByText("inside"));
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.mouseDown(screen.getByRole("presentation"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("ignores backdrop clicks when closeOnBackdrop is false", () => {
    const onClose = vi.fn();
    render(
      <Modal open title="Settings" onClose={onClose} closeOnBackdrop={false}>
        <p>body</p>
      </Modal>
    );
    fireEvent.mouseDown(screen.getByRole("presentation"));
    expect(onClose).not.toHaveBeenCalled();
  });

  it("moves focus to the first focusable element on open and restores it on close", async () => {
    const { rerender } = render(
      <div>
        <button>outside focus</button>
        <Modal open title="Settings" onClose={() => {}}>
          <ClickThrough />
        </Modal>
      </div>
    );
    expect(document.activeElement).toBe(screen.getByText("first"));

    // Save-restore: focus something outside, close, focus returns.
    const outside = screen.getByText("outside focus");
    outside.focus();
    rerender(
      <div>
        <button>outside focus</button>
        <Modal open={false} title="Settings" onClose={() => {}}>
          <ClickThrough />
        </Modal>
      </div>
    );
    expect(document.activeElement).toBe(outside);
  });

  it("traps Tab cycling inside the dialog", async () => {
    const user = userEvent.setup();
    render(
      <Modal open title="Settings" onClose={() => {}}>
        <ClickThrough />
      </Modal>
    );
    screen.getByText("first").focus();
    await user.tab();
    expect(document.activeElement).toBe(screen.getByText("second"));
    await user.tab();
    expect(document.activeElement).toBe(screen.getByTestId("text-input"));
    // Wraps back to the first focusable.
    await user.tab();
    expect(document.activeElement).toBe(screen.getByText("first"));
  });

  it("stacks nested modals above the parent via inline z-index", () => {
    render(<ModalHost nested />);
    const dialogs = screen.getAllByRole("dialog");
    expect(dialogs).toHaveLength(2);

    const zOf = (el: HTMLElement) => {
      let node: HTMLElement | null = el;
      while (node) {
        const z = node.style?.zIndex;
        if (z) return Number(z);
        node = node.parentElement;
      }
      return 0;
    };

    const outer = screen.getByRole("dialog", { name: "Settings" });
    const nested = screen.getByRole("dialog", { name: "Nested" });
    expect(dialogs).toContain(outer);
    expect(dialogs).toContain(nested);
    // Baseline: a single modal clears the app's z-50 overlays.
    expect(Math.min(zOf(outer), zOf(nested))).toBeGreaterThanOrEqual(60);
    expect(zOf(nested)).toBeGreaterThan(zOf(outer));
  });
});