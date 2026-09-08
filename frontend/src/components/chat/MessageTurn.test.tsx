import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { MessageTurn, formatMessageTimestamp } from "./MessageTurn";
import type { Message } from "@/types";

describe("formatMessageTimestamp", () => {
  it("formats an ISO timestamp as YYYY-MM-DD HH:MM:SS in local time", () => {
    // Build the ISO string from local components so the expected wall-clock
    // time is timezone-independent.
    const iso = new Date(2026, 0, 1, 14, 30, 5).toISOString();
    expect(formatMessageTimestamp(iso)).toBe("2026-01-01 14:30:05");
  });

  it("zero-pads single-digit months, days, hours, minutes and seconds", () => {
    const iso = new Date(2026, 2, 4, 5, 6, 7).toISOString();
    expect(formatMessageTimestamp(iso)).toBe("2026-03-04 05:06:07");
  });

  it("returns an empty string for a missing timestamp", () => {
    expect(formatMessageTimestamp(undefined)).toBe("");
  });

  it("returns an empty string for an invalid timestamp", () => {
    expect(formatMessageTimestamp("not-a-date")).toBe("");
  });
});

describe("MessageTurn timestamps", () => {
  const baseTurn = {
    id: "turn-1",
    steps: [],
    isStreaming: false,
  };

  const defaultProps = {
    turn: baseTurn,
    running: false,
    expandedTurns: new Set<string>(),
    toggleExpand: vi.fn(),
    collapsedSteps: new Set<string>(),
    toggleStepExpand: vi.fn(),
    getMessageNestingLevel: () => 0,
    activeInterrupt: null,
    handleSendHumanResponse: vi.fn(),
    handleSendToolApproval: vi.fn(),
    inlineInputRef: { current: null },
    renderMessageContent: (content: string) => <div>{content}</div>,
  };

  const userMessage: Message = {
    id: "msg-user",
    conversation_id: "conv-1",
    role: "user",
    content: "What is the weather?",
    created_at: new Date(2026, 0, 1, 14, 30, 5).toISOString(),
  };

  const finalAnswer: Message = {
    id: "msg-final",
    conversation_id: "conv-1",
    role: "assistant",
    content: "It is sunny.",
    agent_name: "WeatherAgent",
    event_type: "final_answer",
    created_at: new Date(2026, 0, 1, 14, 30, 42).toISOString(),
  };

  it("shows a grey timestamp below the user bubble", () => {
    render(
      <MessageTurn
        {...defaultProps}
        turn={{ ...baseTurn, userMessage, isStreaming: false }}
      />,
    );

    const timestamp = screen.getByTitle("2026-01-01 14:30:05");
    expect(timestamp).toBeInTheDocument();
    expect(timestamp.tagName).toBe("TIME");
    expect(timestamp.className).toContain("text-[var(--color-text-tertiary)]");
  });

  it("shows a grey timestamp below the final answer bubble", () => {
    render(
      <MessageTurn
        {...defaultProps}
        turn={{ ...baseTurn, userMessage, finalAnswer }}
      />,
    );

    const timestamp = screen.getByTitle("2026-01-01 14:30:42");
    expect(timestamp).toBeInTheDocument();
    expect(timestamp.tagName).toBe("TIME");
    expect(timestamp.className).toContain("text-[var(--color-text-tertiary)]");
  });

  it("aligns the user timestamp to the right and the answer timestamp to the left", () => {
    render(
      <MessageTurn
        {...defaultProps}
        turn={{ ...baseTurn, userMessage, finalAnswer }}
      />,
    );

    const userTimestamp = screen.getByTitle("2026-01-01 14:30:05");
    const answerTimestamp = screen.getByTitle("2026-01-01 14:30:42");
    expect(userTimestamp.closest(".items-end")).not.toBeNull();
    expect(answerTimestamp.closest(".items-start")).not.toBeNull();
  });

  it("omits the timestamp when created_at is missing", () => {
    render(
      <MessageTurn
        {...defaultProps}
        turn={{
          ...baseTurn,
          userMessage: { ...userMessage, created_at: undefined as unknown as string },
        }}
      />,
    );

    expect(document.querySelectorAll("time")).toHaveLength(0);
  });
});