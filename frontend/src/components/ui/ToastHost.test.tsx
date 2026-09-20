import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ToastHost } from "@/components/ui/ToastHost";
import { useToastStore, toast } from "@/store/toastStore";

afterEach(() => {
  cleanup();
  useToastStore.setState({ toasts: [] });
});

describe("ToastHost", () => {
  it("renders nothing when there are no toasts", () => {
    render(<ToastHost />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("renders a toast dispatched via the toast API", async () => {
    render(<ToastHost />);
    toast.error("Failed to delete document");
    expect(await screen.findByRole("status")).toHaveTextContent("Failed to delete document");
  });

  it("stacks multiple toasts", async () => {
    render(<ToastHost />);
    toast.error("first error");
    toast.success("second success");
    await waitFor(() => {
      expect(screen.getAllByRole("status")).toHaveLength(2);
    });
  });

  it("dismisses a toast when its close button is clicked", async () => {
    const user = userEvent.setup();
    render(<ToastHost />);
    toast.info("dismiss me");
    await screen.findByRole("status");
    await user.click(screen.getByRole("button", { name: "Dismiss notification" }));
    await waitFor(() => {
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });
  });
});
