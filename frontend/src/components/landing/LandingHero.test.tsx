import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LandingHero } from "./LandingHero";

describe("LandingHero", () => {
  it("renders New Canvas and Import Canvas actions and fires their handlers", async () => {
    const user = userEvent.setup();
    const onCreateCanvas = vi.fn();
    const onImportClick = vi.fn();
    const onChatClick = vi.fn();

    render(
      <LandingHero
        hasCanvases={false}
        loading={false}
        onCreateCanvas={onCreateCanvas}
        onImportClick={onImportClick}
        onChatClick={onChatClick}
      />
    );

    expect(screen.getByText("New Canvas")).toBeInTheDocument();
    expect(screen.getByText("Import Canvas")).toBeInTheDocument();
    expect(screen.queryByText("Agent Chat")).not.toBeInTheDocument();

    await user.click(screen.getByText("New Canvas"));
    expect(onCreateCanvas).toHaveBeenCalledTimes(1);

    await user.click(screen.getByText("Import Canvas"));
    expect(onImportClick).toHaveBeenCalledTimes(1);
  });

  it("shows the Agent Chat node only when canvases exist, and fires its handler", async () => {
    const user = userEvent.setup();
    const onChatClick = vi.fn();

    render(
      <LandingHero
        hasCanvases={true}
        loading={false}
        onCreateCanvas={vi.fn()}
        onImportClick={vi.fn()}
        onChatClick={onChatClick}
      />
    );

    const chatNode = screen.getByText("Agent Chat");
    expect(chatNode).toBeInTheDocument();

    await user.click(chatNode);
    expect(onChatClick).toHaveBeenCalledTimes(1);
  });

  it("disables all action nodes while loading", () => {
    render(
      <LandingHero
        hasCanvases={true}
        loading={true}
        onCreateCanvas={vi.fn()}
        onImportClick={vi.fn()}
        onChatClick={vi.fn()}
      />
    );

    expect(screen.getByText("New Canvas").closest("button")).toBeDisabled();
    expect(screen.getByText("Import Canvas").closest("button")).toBeDisabled();
    expect(screen.getByText("Agent Chat").closest("button")).toBeDisabled();
  });
});
