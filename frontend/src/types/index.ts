export interface AgentNodeData {
  id: string;
  name: string;
  role: string;
  instructions: string;
  modelName: string;
  agentType: "worker" | "router";
  enableMemory?: boolean;
  enableConversationHistory?: boolean;
}

export interface ToolNodeData {
  id: string;
  name: string;
  code: string;
  packages?: string;
}

export type ExecutionEvent =
  | { type: "run_start"; canvas_id: string; node_id?: string }
  | { type: "agent_start"; agent: string; agentType?: string; node_id?: string }
  | { type: "thought"; agent: string; content: string; node_id?: string }
  | { type: "tool_start"; agent: string; tool: string; input?: Record<string, unknown>; node_id?: string }
  | { type: "tool_result"; agent: string; tool: string; output: string; node_id?: string }
  | { type: "handoff"; from: string; to: string; node_id?: string }
  | { type: "final_answer"; agent?: string; content: string; node_id?: string }
  | { type: "run_complete"; result: string }
  | { type: "error"; message: string; agent?: string; node_id?: string };

export type ExecutionStatus = "idle" | "running" | "done" | "error";

export interface ToolArgument {
  name: string;
  type: string;
}

export interface CanvasSavePayload {
  name: string;
  nodes: {
    agents: {
      id: string;
      name: string;
      role: string;
      instructions: string;
      model_name: string;
      agent_type: string;
      enable_memory: boolean;
      enable_conversation_history: boolean;
      position_x: number;
      position_y: number;
    }[];
    tools: {
      id:string;
      name: string;
      code: string;
      packages?: string;
      args: ToolArgument[];
      position_x: number;
      position_y: number;
    }[];
  };
  edges: {
    id: string;
    source_node_id: string;
    target_node_id: string;
    edge_type: string;
  }[];
}

export interface CanvasResponse {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  nodes: {
    agents: Array<{
      id: string;
      canvas_id: string;
      name: string;
      role: string;
      instructions: string;
      model_name: string;
      agent_type: string;
      enable_memory: boolean;
      enable_conversation_history: boolean;
      position_x: number;
      position_y: number;
    }>;
    tools: Array<{
      id: string;
      canvas_id: string;
      name: string;
      code: string;
      packages?: string;
      args: ToolArgument[];
      position_x: number;
      position_y: number;
    }>;
  };
  edges: Array<{
    id: string;
    canvas_id: string;
    source_node_id: string;
    target_node_id: string;
    edge_type: string;
  }>;
}

export interface CanvasListItem {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationSummary {
  id: string;
  canvas_id: string;
  name: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: string;
  content: string;
  agent_name?: string | null;
  node_id?: string | null;
  event_type?: string | null;
  created_at: string;
}

export interface Conversation {
  id: string;
  canvas_id: string;
  name: string;
  status: string;
  created_at: string;
  updated_at: string;
  messages: Message[];
}

export interface ToolInspectResponse {
  function_name: string;
  arguments: Array<{
    name: string;
    type_hint: string;
    default_value: string | null;
  }>;
}

export interface ToolTestResponse {
  success: boolean;
  output: string;
  execution_time_ms: number;
}
