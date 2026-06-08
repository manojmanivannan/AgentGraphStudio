import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useCanvasStore } from "@/store/canvasStore";
import { TopBar } from "./TopBar";

describe("TopBar", () => {
  it("renders the canvas name and handles reset on home button click", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setCanvas("canvas-test-id", "Mock Canvas Name");

    render(<TopBar />);

    expect(screen.getByDisplayValue("Mock Canvas Name")).toBeInTheDocument();

    const homeButton = screen.getByTestId("home-button");
    expect(homeButton).toBeInTheDocument();

    await user.click(homeButton);

    expect(useCanvasStore.getState().canvasId).toBeNull();
  });
});
