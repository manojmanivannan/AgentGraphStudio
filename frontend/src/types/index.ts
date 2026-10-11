export interface User {
  id: string;
  email: string;
  created_at: string;
}

export interface AuthResponse {
  user: User;
}

export type ProviderProfileId =
  | "external_ollama"
  | "docker_ollama"
  | "openai"
  | "openrouter"
  | "custom";

export interface ProviderSettingsForm {
  profile: ProviderProfileId;
  llm_provider_type: string;
  llm_base_url: string;
  llm_model: string;
  mem0_embedder_model: string;
  mem0_embedder_dimensions: number;
}

export interface ProviderSettings extends ProviderSettingsForm {
  /** The key itself is never returned by the API. */
  api_key_set: boolean;
  source: "env" | "database";
}

// --- MCP server registry ---

export interface McpServer {
  id: string;
  name: string;
  url: string;
  credential_header: string | null;
  /** The credential itself is never returned by the API. */
  credential_set: boolean;
  /** Masked preview: bullets plus at most the last 4 characters. */
  credential_preview: string | null;
  /** Non-null when the endpoint uses plain "http://" (§5.1). */
  url_warning: string | null;
}

export interface McpServerForm {
  name: string;
  url: string;
  credential_header: string | null;
}

export interface ProviderCheckResult {
  name: string;
  ok: boolean;
  detail: string;
  latency_ms: number;
}

export interface ProviderTestResponse {
  ok: boolean;
  checks: ProviderCheckResult[];
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
  ragTopK?: number;
  enableHitl?: boolean;
  isEntryPoint?: boolean;
}

export interface AgentDocument {
  id: string;
  name: string;
  created_at: string;
}

/** One enabled tool of an MCP-backed Tool Node's grant (spec §2.1/#132):
 * per-tool approval granularity (#119 Q9). Wire shape (snake_case, matches
 * the backend payloads and responses). */
export interface McpToolGrant {
  name: string;
  requires_approval: boolean;
}

/** Same grant entry in ReactFlow node-data shape (camelCase, mirrors
 * `ToolNodeData` conventions). */
export interface McpToolGrantData {
  name: string;
  requiresApproval: boolean;
}

/** One tool inside an exported MCP metadata snapshot (spec §2.3/#136). */
export interface McpReferenceSnapshotTool {
  name: string;
  description: string | null;
  input_schema: Record<string, unknown>;
}

/** Metadata snapshot captured live at export time (spec §2.3); `captured` is
 * false when the live fetch failed — `detail` then carries the failure summary. */
export interface McpReferenceSnapshot {
  captured: boolean;
  server_name: string | null;
  server_version: string | null;
  protocol_revision: string | null;
  detail: string;
  tools: McpReferenceSnapshotTool[];
}

/** Server reference carried by ZIP export/import (#136, spec §2.3/§5.1):
 * resolved registered name + URL, else `resolved: false`. The URL is never
 * imported — this block reappears on imported nodes as reference metadata
 * only. */
export interface McpServerReference {
  resolved: boolean;
  name: string | null;
  url: string | null;
  snapshot: McpReferenceSnapshot | null;
}

export interface ToolNodeData {
  id: string;
  name: string;
  code: string;
  packages?: string;
  requiresApproval?: boolean;
  /** Non-null ⇒ MCP-backed node: the node grants a subset of one registered
   * server's tools and `code`/`args` stay empty (#132). */
  mcpServerId?: string | null;
  /** Enabled-tools selection for the server grant (camelCase mirrors the
   * other node-data fields). */
  mcpTools?: McpToolGrantData[];
  /** Import-only reference metadata (#136): null unless the node was just
   * imported from a manifest carrying an MCP reference. */
  mcpReference?: McpServerReference | null;
}

export type AttachmentFileType =
  | "csv"
  | "json"
  | "text"
  | "python"
  | "yaml"
  | "image"
  | "pdf"
  | "binary"
  | string;

export interface AttachmentProducedArgs {
  attachment_id: string;
  name: string;
  file_type: string;
  source: string;
}

export interface AttachmentConsumedArgs {
  attachment_id: string;
  name: string;
  file_type: string;
  source?: string;
  delivery_method: string;
  original_filename?: string | null;
}

export interface AttachmentNodeData {
  id: string;
  name: string;
  fileType: AttachmentFileType;
  deliveryMethod?: "inline" | "file_path";
  description?: string;
}

export interface ChatAttachmentUploadResult {
  filename: string;
  success: boolean;
  attachment_id?: string | null;
  node_id?: string | null;
  file_type?: string | null;
  error?: string | null;
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
  | { type: "attachment_produced"; attachment_id: string; name: string; file_type: string; source: string; conversation_id?: string; agent?: string; node_id?: string; original_filename?: string | null }
  | { type: "attachment_consumed"; attachment_id: string; name: string; file_type: string; source?: string; delivery_method: string; conversation_id?: string; agent?: string; node_id?: string; original_filename?: string | null }
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
      rag_top_k: number;
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
      mcp_server_id: string | null;
      mcp_tools: McpToolGrant[];
      position_x: number;
      position_y: number;
    }[];
    attachments?: {
      id: string;
      name: string;
      file_type: string;
      delivery_method: string;
      description: string;
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
      rag_top_k: number;
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
      mcp_server_id: string | null;
      mcp_tools: McpToolGrant[];
      /** Import-only reference metadata (#136) — null outside import responses. */
      mcp_reference?: McpServerReference | null;
      position_x: number;
      position_y: number;
    }>;
    attachments?: Array<{
      id: string;
      canvas_id: string;
      name: string;
      file_type: string;
      delivery_method: string;
      description: string;
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
  /** Import notices (#136): e.g. an MCP grant imported not-yet-granting. */
  warnings?: string[];
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
