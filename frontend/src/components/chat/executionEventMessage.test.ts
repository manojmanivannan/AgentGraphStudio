import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import {
  classifyToolResult,
  executionEventToMessage,
} from "./executionEventMessage";
import type { ExecutionEvent } from "@/types";


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
      tool: "get_weather_forecast",
      created_at: "2026-01-01T00:00:00.000Z",
    });
  });

  it("maps coding tool results with python_code input args", () => {
    const code = "import math\nprint(math.pi)";
    const message = executionEventToMessage(
      {
        type: "tool_result",
        agent: "CoderAgent",
        tool: "run_code",
        input: { python_code: code },
        output: "3.141592653589793\n",
        node_id: "agent-1",
      },
      baseContext
    );

    expect(message).toEqual({
      id: "msg-1",
      conversation_id: "conv-1",
      role: "tool",
      content: "3.141592653589793\n",
      agent_name: "run_code",
      node_id: "agent-1",
      event_type: "tool_result",
      tool: "run_code",
      args: { python_code: code },
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

  it("maps human_input_response to user messages", () => {
    const message = executionEventToMessage(
      {
        type: "human_input_response",
        request_id: "req-1",
        content: "Hello",
      },
      baseContext
    );

    expect(message).toEqual({
      id: "msg-1",
      conversation_id: "conv-1",
      role: "user",
      content: "Hello",
      event_type: "human_input_response",
      created_at: "2026-01-01T00:00:00.000Z",
    });
  });

  it("maps interrupt_response with content to user messages", () => {
    const message = executionEventToMessage(
      {
        type: "interrupt_response",
        request_id: "req-1",
        content: "Hi there",
      },
      baseContext
    );

    expect(message).toEqual({
      id: "msg-1",
      conversation_id: "conv-1",
      role: "user",
      content: "Hi there",
      event_type: "human_input_response",
      created_at: "2026-01-01T00:00:00.000Z",
    });
  });

  it("returns null for tool_approval_response", () => {
    const message = executionEventToMessage(
      {
        type: "tool_approval_response",
        request_id: "req-1",
        approved: true,
      },
      baseContext
    );

    expect(message).toBeNull();
  });

  it("maps attachment_produced events to assistant attachment transcript messages", () => {
    const event: ExecutionEvent = {
      type: "attachment_produced",
      attachment_id: "attachment-1",
      name: "report.csv",
      file_type: "csv",
      source: "agent_output",
      agent: "ReportAgent",
      node_id: "node-3",
    };

    const message = executionEventToMessage(event, baseContext);

    expect(message).toEqual({
      id: "msg-1",
      conversation_id: "conv-1",
      role: "assistant",
      content: "",
      agent_name: "ReportAgent",
      node_id: "node-3",
      event_type: "attachment_produced",
      args: {
        attachment_id: "attachment-1",
        name: "report.csv",
        file_type: "csv",
        source: "agent_output",
      },
      created_at: "2026-01-01T00:00:00.000Z",
    });
  });

  it.each(["inline", "file_path", "dual", "manifest_only"])(
    "maps attachment_consumed events with delivery_method=%s to assistant attachment transcript messages",
    (deliveryMethod) => {
      const event = {
        type: "attachment_consumed",
        attachment_id: "attachment-1",
        name: "report.csv",
        file_type: "csv",
        source: "chat_upload",
        delivery_method: deliveryMethod,
        agent: "ReportAgent",
        node_id: "node-3",
        original_filename: "uploaded-report.csv",
      } as const;

      const message = executionEventToMessage(event as ExecutionEvent, baseContext);

      expect(message).toEqual({
        id: "msg-1",
        conversation_id: "conv-1",
        role: "assistant",
        content: "",
        agent_name: "ReportAgent",
        node_id: "node-3",
        event_type: "attachment_consumed",
        args: {
          attachment_id: "attachment-1",
          name: "report.csv",
          file_type: "csv",
          source: "chat_upload",
          delivery_method: deliveryMethod,
          original_filename: "uploaded-report.csv",
        },
        created_at: "2026-01-01T00:00:00.000Z",
      });
    }
  );
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