export interface AgentNodeData {
  id: string;
  name: string;
  role: string;
  instructions: string;
  modelName: string;
}

export interface ToolNodeData {
  id: string;
  name: string;
  code: string;
}

export type ExecutionEvent =
  | { type: "run_start"; canvas_id: string }
  | { type: "agent_start"; agent: string }
  | { type: "thought"; agent: string; content: string }
  | { type: "tool_call"; agent: string; tool: string; input: Record<string, unknown> }
  | { type: "tool_result"; agent: string; tool: string; output: string }
  | { type: "handoff"; from: string; to: string }
  | { type: "final_answer"; agent?: string; content: string }
  | { type: "run_complete"; result: string }
  | { type: "error"; message: string; agent?: string };

export type ExecutionStatus = "idle" | "running" | "done" | "error";

export interface CanvasSavePayload {
  name: string;
  nodes: {
    agents: {
      id: string;
      name: string;
      role: string;
      instructions: string;
      model_name: string;
      position_x: number;
      position_y: number;
    }[];
    tools: {
      id: string;
      name: string;
      code: string;
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
      position_x: number;
      position_y: number;
    }>;
    tools: Array<{
      id: string;
      canvas_id: string;
      name: string;
      code: string;
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
