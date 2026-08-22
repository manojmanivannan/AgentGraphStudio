import type { Edge, Node } from "@xyflow/react";
import type {
  AgentNodeData,
  CanvasResponse,
  CanvasSavePayload,
  ToolArgument,
  ToolNodeData,
} from "@/types";

const DEFAULT_AGENT_MODEL = "ollama:llama3.1";
const DEFAULT_AGENT_TYPE = "worker";
const DEFAULT_RAG_CHUNK_SIZE = 1000;
const AGENT_NODE_WIDTH = 280;
const TOOL_NODE_WIDTH = 220;

type CanvasGraph = {
  canvasName: string;
  nodes: Node[];
  edges: Edge[];
};

type DecodedCanvasGraph = {
  nodes: Node[];
  edges: Edge[];
};

function asAgentNodeData(node: Node): Partial<AgentNodeData> {
  return (node.data ?? {}) as Partial<AgentNodeData>;
}

function asToolNodeData(node: Node): Partial<ToolNodeData & { args?: ToolArgument[] }> {
  return (node.data ?? {}) as Partial<ToolNodeData & { args?: ToolArgument[] }>;
}

export function encodeCanvasGraph({ canvasName, nodes, edges }: CanvasGraph): CanvasSavePayload {
  return {
    name: canvasName,
    nodes: {
      agents: nodes
        .filter((node) => node.type === "agent")
        .map((node) => {
          const data = asAgentNodeData(node);
          return {
            id: node.id,
            name: data.name ?? "Agent",
            role: data.role ?? "",
            instructions: data.instructions ?? "",
            model_name: data.modelName ?? DEFAULT_AGENT_MODEL,
            agent_type: data.agentType ?? DEFAULT_AGENT_TYPE,
            enable_plotting: data.enablePlotting ?? false,
            enable_coding: data.enableCoding ?? false,
            enable_network: data.enableNetwork ?? false,
            enable_memory: data.enableMemory ?? false,
            enable_conversation_history: data.enableConversationHistory ?? false,
            enable_rag: data.enableRag ?? false,
            rag_chunk_size: data.ragChunkSize ?? DEFAULT_RAG_CHUNK_SIZE,
            is_entry_point: data.isEntryPoint ?? false,
            enable_hitl: data.enableHitl ?? false,
            position_x: node.position.x,
            position_y: node.position.y,
          };
        }),
      tools: nodes
        .filter((node) => node.type === "tool")
        .map((node) => {
          const data = asToolNodeData(node);
          return {
            id: node.id,
            name: data.name ?? "Tool",
            code: data.code ?? "",
            packages: data.packages ?? "",
            args: data.args ?? [],
            requires_approval: data.requiresApproval ?? false,
            position_x: node.position.x,
            position_y: node.position.y,
          };
        }),
    },
    edges: edges.map((edge) => ({
      id: edge.id,
      source_node_id: edge.source,
      target_node_id: edge.target,
      edge_type: ((edge.data ?? {}) as { edgeType?: string }).edgeType ?? "tool_access",
    })),
  };
}

export function decodeCanvasResponse(canvas: CanvasResponse): DecodedCanvasGraph {
  return {
    nodes: [
      ...canvas.nodes.agents.map((agent) => ({
        id: agent.id,
        type: "agent",
        position: { x: agent.position_x, y: agent.position_y },
        style: { width: AGENT_NODE_WIDTH },
        data: {
          id: agent.id,
          name: agent.name,
          role: agent.role,
          instructions: agent.instructions,
          modelName: agent.model_name,
          agentType: agent.agent_type as AgentNodeData["agentType"],
          enablePlotting: agent.enable_plotting,
          enableCoding: agent.enable_coding,
          enableNetwork: agent.enable_network,
          enableMemory: agent.enable_memory,
          enableConversationHistory: agent.enable_conversation_history,
          enableRag: agent.enable_rag,
          ragChunkSize: agent.rag_chunk_size,
          isEntryPoint: agent.is_entry_point,
          enableHitl: agent.enable_hitl,
        },
      })),
      ...canvas.nodes.tools.map((tool) => ({
        id: tool.id,
        type: "tool",
        position: { x: tool.position_x, y: tool.position_y },
        style: { width: TOOL_NODE_WIDTH },
        data: {
          id: tool.id,
          name: tool.name,
          code: tool.code,
          packages: tool.packages ?? "",
          args: tool.args,
          requiresApproval: tool.requires_approval,
        },
      })),
    ],
    edges: canvas.edges.map((edge) => ({
      id: edge.id,
      source: edge.source_node_id,
      target: edge.target_node_id,
      data: { edgeType: edge.edge_type },
    })),
  };
}
