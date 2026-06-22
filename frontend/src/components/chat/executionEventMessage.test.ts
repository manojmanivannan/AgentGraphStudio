import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import {
  classifyToolResult,
  executionEventToMessage,
} from "./executionEventMessage";


interface ToolResultContractCase {
  tool_name: string;
  fallback_agent_name: string;
  expected_agent_name: string;
  expected_event_type: "response" | "tool_result";
}


const contractCases = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      "src/contracts/transcript_tool_result_contract.json"
    ),
    "utf-8"
  )
) as ToolResultContractCase[];


describe("executionEventToMessage", () => {
  const baseContext = {
    conversationId: "conv-1",
    messageId: "msg-1",
    createdAt: "2026-01-01T00:00:00.000Z",
  };

  it("maps handoff tool results to response messages", () => {
    const message = executionEventToMessage(
      {
        type: "tool_result",
        agent: "Router",
        tool: "transfer_to_WeatherAgent",
        output: "Cloudy in Mumbai",
        node_id: "node-1",
      },
      baseContext
    );

    expect(message).toEqual({
      id: "msg-1",
      conversation_id: "conv-1",
      role: "assistant",
      content: "Cloudy in Mumbai",
      agent_name: "WeatherAgent",
      node_id: "node-1",
      event_type: "response",
      created_at: "2026-01-01T00:00:00.000Z",
    });
  });

  it("maps non-handoff tool results to tool transcript messages", () => {
    const message = executionEventToMessage(
      {
        type: "tool_result",
        agent: "WeatherAgent",
        tool: "get_weather_forecast",
        output: "Sunny in Chennai",
        node_id: "tool-node-1",
      },
      baseContext
    );

    expect(message).toEqual({
      id: "msg-1",
      conversation_id: "conv-1",
      role: "tool",
      content: "Sunny in Chennai",
      agent_name: "get_weather_forecast",
      node_id: "tool-node-1",
      event_type: "tool_result",
      created_at: "2026-01-01T00:00:00.000Z",
    });
  });

  it("maps handoff events to system transcript messages", () => {
    const message = executionEventToMessage(
      {
        type: "handoff",
        from: "Router",
        to: "WeatherAgent",
        node_id: "node-2",
      },
      baseContext
    );

    expect(message).toEqual({
      id: "msg-1",
      conversation_id: "conv-1",
      role: "system",
      content: "Delegating to WeatherAgent...",
      agent_name: "Router",
      node_id: "node-2",
      event_type: "handoff",
      created_at: "2026-01-01T00:00:00.000Z",
    });
  });

  it("returns null for transport-only events", () => {
    const message = executionEventToMessage(
      {
        type: "run_complete",
        result: "done",
      },
      baseContext
    );

    expect(message).toBeNull();
  });
});


describe("classifyToolResult", () => {
  it.each(contractCases)("matches shared contract: $tool_name", (testCase) => {
    const result = classifyToolResult(
      testCase.tool_name,
      testCase.fallback_agent_name
    );

    expect(result).toEqual({
      agentName: testCase.expected_agent_name,
      eventType: testCase.expected_event_type,
    });
  });
});