export interface User {
  id: string;
  email: string;
  created_at: string;
}

export interface AuthResponse {
  user: User;
}

export interface AgentNodeData {
  id: string;
  name: string;
  role: string;
  instructions: string;
  modelName: string;
  agentType: "worker" | "router";
  enablePlotting?: boolean;
  enableCoding?: boolean;
  enableNetwork?: boolean;
  enableMemory?: boolean;
  enableConversationHistory?: boolean;
  enableRag?: boolean;
  ragChunkSize?: number;
  enableHitl?: boolean;
  isEntryPoint?: boolean;
}

export interface AgentDocument {
  id: string;
  name: string;
  created_at: string;
}

export interface ToolNodeData {
  id: string;
  name: string;
  code: string;
  packages?: string;
  requiresApproval?: boolean;
}

type ExecutionEventBase = {
  run_id?: string;
  sequence?: number;
};

export type ExecutionEvent = ExecutionEventBase & (
  | { type: "run_start"; canvas_id: string; node_id?: string }
  | { type: "agent_start"; agent: string; agentType?: string; node_id?: string }
  | { type: "thought"; agent: string; content: string; node_id?: string }
  | { type: "tool_start"; agent: string; tool: string; input?: Record<string, unknown>; args?: Record<string, unknown>; node_id?: string }
  | { type: "tool_result"; agent: string; tool: string; output: string; input?: Record<string, unknown>; args?: Record<string, unknown>; node_id?: string }
  | { type: "handoff"; from: string; to: string; node_id?: string }
  | { type: "final_answer"; agent?: string; content: string; node_id?: string }
  | { type: "run_complete"; result: string }
  | { type: "run_aborted"; message: string }
  | { type: "error"; message: string; agent?: string; node_id?: string }
  | { type: "warning"; message: string; agent?: string; node_id?: string }
  | { type: "human_input_request"; request_id: string; question: string; agent: string; node_id?: string }
  | { type: "tool_approval_request"; request_id: string; tool: string; args?: Record<string, unknown>; agent: string; node_id?: string }
  | { type: "human_input_response"; request_id: string; content: string }
  | { type: "tool_approval_response"; request_id: string; approved: boolean }
  | { type: "interrupt_response"; request_id: string; response?: any; content?: string }
  | { type: "conversation_renamed"; conversation_id: string; name: string }
  | { type: "run_queued"; run_id: string }
);

export interface ActiveRunResponse {
  run_id: string;
  conversation_id: string;
  status: string;
  replay_cursor: string | null;
}

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
      enable_plotting: boolean;
      enable_coding: boolean;
      enable_network: boolean;
      enable_hitl: boolean;
      enable_memory: boolean;
      enable_conversation_history: boolean;
      enable_rag: boolean;
      rag_chunk_size: number;
      is_entry_point: boolean;
      position_x: number;
      position_y: number;
    }[];
    tools: {
      id: string;
      name: string;
      code: string;
      packages?: string;
      args: ToolArgument[];
      requires_approval: boolean;
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
      enable_plotting: boolean;
      enable_coding: boolean;
      enable_network: boolean;
      enable_hitl: boolean;
      enable_memory: boolean;
      enable_conversation_history: boolean;
      enable_rag: boolean;
      rag_chunk_size: number;
      is_entry_point: boolean;
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
      requires_approval: boolean;
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
  tool?: string | null;
  args?: Record<string, any> | null;
  created_at: string;
  request_id?: string | null;
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
