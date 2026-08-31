import { beforeEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useThemeStore } from "@/store/themeStore";
import { AppearanceSection } from "@/components/settings/sections/AppearanceSection";
import { ThemeToggle } from "@/components/ThemeToggle";

describe("AppearanceSection", () => {
  beforeEach(() => {
    useThemeStore.setState({ theme: "dark" });
    localStorage.removeItem("agent-builder-theme");
    document.documentElement.removeAttribute("data-theme");
  });

  it("renders a theme radiogroup reflecting the current theme", () => {
    useThemeStore.setState({ theme: "dark" });
    render(<AppearanceSection />);
    const group = screen.getByRole("radiogroup", { name: /theme/i });
    expect(group).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /dark/i })).toBeChecked();
    expect(screen.getByRole("radio", { name: /light/i })).not.toBeChecked();
  });

  it("switches the theme when a card is selected", async () => {
    const user = userEvent.setup();
    render(<AppearanceSection />);

    await user.click(screen.getByRole("radio", { name: /light/i }));

    expect(useThemeStore.getState().theme).toBe("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(localStorage.getItem("agent-builder-theme")).toBe("light");
  });

  it("stays in sync with the ThemeToggle (same store)", async () => {
    const user = userEvent.setup();
    render(
      <div>
        <AppearanceSection />
        <ThemeToggle />
      </div>
    );

    // The quick toggle flips the theme and the radiogroup follows.
    await user.click(screen.getByTestId("theme-toggle"));
    expect(
      screen.getByRole("radio", { name: /light/i })
    ).toBeChecked();

    // And selecting a card moves the toggle's state too.
    await user.click(screen.getByRole("radio", { name: /dark/i }));
    expect(useThemeStore.getState().theme).toBe("dark");
  });
});