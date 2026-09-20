import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Home } from "lucide-react";
import { RailItem } from "./RailItem";

describe("RailItem", () => {
  it("exposes an accessible name via aria-label matching the label", () => {
    render(<RailItem icon={Home} label="Home" onClick={vi.fn()} />);

    const button = screen.getByRole("button", { name: "Home" });
    expect(button).toHaveAttribute("aria-label", "Home");
    expect(button).toHaveAttribute("title", "Home");
  });
});
