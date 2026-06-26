import type { ExecutionEvent, Message } from "@/types";

const HANDOFF_TOOL_PREFIX = "transfer_to_";


interface ExecutionEventMessageContext {
  conversationId: string;
  messageId: string;
  createdAt: string;
}


interface ToolResultClassification {
  agentName: string;
  eventType: "response" | "tool_result";
}


export function classifyToolResult(
  toolName: string | undefined,
  fallbackAgentName: string
): ToolResultClassification {
  const normalizedToolName = toolName ?? "";
  const isHandoffTool = normalizedToolName.startsWith(HANDOFF_TOOL_PREFIX);
  return {
    agentName: normalizedToolName
      ? normalizedToolName.replace(HANDOFF_TOOL_PREFIX, "")
      : fallbackAgentName,
    eventType: isHandoffTool ? "response" : "tool_result",
  };
}


export function executionEventToMessage(
  event: ExecutionEvent,
  context: ExecutionEventMessageContext
): Message | null {
  const baseMessage = {
    id: context.messageId,
    conversation_id: context.conversationId,
    created_at: context.createdAt,
  };

  if (event.type === "error") {
    return {
      ...baseMessage,
      role: "system",
      content: event.message,
      agent_name: event.agent ?? null,
      node_id: event.node_id ?? null,
      event_type: "error",
    };
  }

  if (event.type === "warning") {
    return {
      ...baseMessage,
      role: "system",
      content: event.message,
      agent_name: event.agent ?? null,
      node_id: event.node_id ?? null,
      event_type: "warning",
    };
  }

  if (event.type === "run_aborted") {
    return {
      ...baseMessage,
      role: "system",
      content: event.message,
      agent_name: null,
      node_id: null,
      event_type: "warning",
    };
  }

  if (event.type === "human_input_request") {
    return {
      ...baseMessage,
      role: "assistant",
      content: event.question,
      agent_name: event.agent,
      node_id: event.node_id ?? null,
      event_type: "human_input_request",
      request_id: event.request_id,
    };
  }

  if (event.type === "tool_approval_request") {
    return {
      ...baseMessage,
      role: "tool",
      content: `Tool approval required: ${event.tool}`,
      agent_name: event.agent,
      node_id: event.node_id ?? null,
      event_type: "tool_approval_request",
      request_id: event.request_id,
      args: event.args ?? null,
    };
  }

  if (event.type === "final_answer") {
    return {
      ...baseMessage,
      role: "assistant",
      content: event.content,
      agent_name: event.agent ?? null,
      node_id: event.node_id ?? null,
      event_type: "final_answer",
    };
  }

  if (event.type === "thought") {
    return {
      ...baseMessage,
      role: "assistant",
      content: event.content,
      agent_name: event.agent,
      node_id: event.node_id ?? null,
      event_type: "thought",
    };
  }

  if (event.type === "handoff") {
    return {
      ...baseMessage,
      role: "system",
      content: `Delegating to ${event.to}...`,
      agent_name: event.from,
      node_id: event.node_id ?? null,
      event_type: "handoff",
    };
  }

  if (event.type === "tool_result") {
    const classification = classifyToolResult(event.tool, event.agent);
    return {
      ...baseMessage,
      role: classification.eventType === "response" ? "assistant" : "tool",
      content: event.output,
      agent_name: classification.agentName,
      node_id: event.node_id ?? null,
      event_type: classification.eventType,
    };
  }

  if (event.type === "human_input_response" || event.type === "interrupt_response") {
    const isToolApproval = (event as any).approved !== undefined || (event as any).type === "tool_approval_response";
    if (isToolApproval) {
      return null;
    }
    const content = (event as any).content || (event as any).response || "";
    return {
      ...baseMessage,
      role: "user",
      content: content,
      event_type: "human_input_response",
    };
  }

  return null;
}