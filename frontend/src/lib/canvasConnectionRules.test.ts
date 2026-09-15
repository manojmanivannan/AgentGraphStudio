import { describe, expect, it } from "vitest";
import { deriveEdgeType, isValidNodeTypeConnection } from "./canvasConnectionRules";

describe("isValidNodeTypeConnection", () => {
  it("allows agent to tool", () => {
    expect(isValidNodeTypeConnection("agent", "tool")).toBe(true);
  });

  it("allows agent to agent", () => {
    expect(isValidNodeTypeConnection("agent", "agent")).toBe(true);
  });

  it("allows agent to attachment (produces)", () => {
    expect(isValidNodeTypeConnection("agent", "attachment")).toBe(true);
  });

  it("allows attachment to agent (consumes)", () => {
    expect(isValidNodeTypeConnection("attachment", "agent")).toBe(true);
  });

  it("rejects attachment to attachment", () => {
    expect(isValidNodeTypeConnection("attachment", "attachment")).toBe(false);
  });

  it("rejects attachment to tool", () => {
    expect(isValidNodeTypeConnection("attachment", "tool")).toBe(false);
  });

  it("rejects tool to attachment", () => {
    expect(isValidNodeTypeConnection("tool", "attachment")).toBe(false);
  });

  it("rejects tool to agent", () => {
    expect(isValidNodeTypeConnection("tool", "agent")).toBe(false);
  });

  it("rejects tool to tool", () => {
    expect(isValidNodeTypeConnection("tool", "tool")).toBe(false);
  });
});

describe("deriveEdgeType", () => {
  it("derives handoff for agent to agent", () => {
    expect(deriveEdgeType("agent", "agent")).toBe("handoff");
  });

  it("derives tool_access for agent to tool", () => {
    expect(deriveEdgeType("agent", "tool")).toBe("tool_access");
  });

  it("derives produces for agent to attachment", () => {
    expect(deriveEdgeType("agent", "attachment")).toBe("produces");
  });

  it("derives consumes for attachment to agent", () => {
    expect(deriveEdgeType("attachment", "agent")).toBe("consumes");
  });
});
