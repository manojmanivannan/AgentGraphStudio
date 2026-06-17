import { describe, expect, it } from "vitest";
import { decodeCanvasResponse, encodeCanvasGraph } from "./canvasGraphCodec";

describe("canvasGraphCodec", () => {
  it("encodes agent, tool, and edge data from store graph into a save payload", () => {
    const result = encodeCanvasGraph({
      canvasName: "Codec Canvas",
      nodes: [
        {
          id: "agent-1",
          type: "agent",
          position: { x: 10, y: 20 },
          data: {
            id: "agent-1",
            name: "Planner",
            role: "Plan work",
            instructions: "Think step by step",
            modelName: "ollama:llama3.1",
            agentType: "worker",
          },
        },
        {
          id: "tool-1",
          type: "tool",
          position: { x: 30, y: 40 },
          data: {
            id: "tool-1",
            name: "Lookup",
            code: "def lookup():\n    return 'ok'",
          },
        },
      ],
      edges: [
        {
          id: "edge-1",
          source: "agent-1",
          target: "tool-1",
          data: { edgeType: "tool_access" },
        },
      ],
    });

    expect(result).toEqual({
      name: "Codec Canvas",
      nodes: {
        agents: [
          {
            id: "agent-1",
            name: "Planner",
            role: "Plan work",
            instructions: "Think step by step",
            model_name: "ollama:llama3.1",
            agent_type: "worker",
            enable_plotting: false,
            enable_memory: false,
            enable_conversation_history: false,
            enable_rag: false,
            rag_chunk_size: 1000,
            position_x: 10,
            position_y: 20,
          },
        ],
        tools: [
          {
            id: "tool-1",
            name: "Lookup",
            code: "def lookup():\n    return 'ok'",
            packages: "",
            args: [],
            position_x: 30,
            position_y: 40,
          },
        ],
      },
      edges: [
        {
          id: "edge-1",
          source_node_id: "agent-1",
          target_node_id: "tool-1",
          edge_type: "tool_access",
        },
      ],
    });
  });

  it("decodes a canvas response into store graph nodes and edges", () => {
    const result = decodeCanvasResponse({
      id: "canvas-1",
      name: "Decoded Canvas",
      created_at: "2026-06-17T00:00:00Z",
      updated_at: "2026-06-17T00:00:00Z",
      nodes: {
        agents: [
          {
            id: "agent-1",
            canvas_id: "canvas-1",
            name: "Planner",
            role: "Plan work",
            instructions: "Think step by step",
            model_name: "ollama:llama3.1",
            agent_type: "router",
            enable_plotting: true,
            enable_memory: true,
            enable_conversation_history: true,
            enable_rag: true,
            rag_chunk_size: 2048,
            position_x: 11,
            position_y: 22,
          },
        ],
        tools: [
          {
            id: "tool-1",
            canvas_id: "canvas-1",
            name: "Lookup",
            code: "def lookup():\n    return 'ok'",
            packages: "requests",
            args: [],
            position_x: 33,
            position_y: 44,
          },
        ],
      },
      edges: [
        {
          id: "edge-1",
          canvas_id: "canvas-1",
          source_node_id: "agent-1",
          target_node_id: "tool-1",
          edge_type: "tool_access",
        },
      ],
    });

    expect(result.nodes).toEqual([
      {
        id: "agent-1",
        type: "agent",
        position: { x: 11, y: 22 },
        style: { width: 280 },
        data: {
          id: "agent-1",
          name: "Planner",
          role: "Plan work",
          instructions: "Think step by step",
          modelName: "ollama:llama3.1",
          agentType: "router",
          enablePlotting: true,
          enableMemory: true,
          enableConversationHistory: true,
          enableRag: true,
          ragChunkSize: 2048,
        },
      },
      {
        id: "tool-1",
        type: "tool",
        position: { x: 33, y: 44 },
        style: { width: 220 },
        data: {
          id: "tool-1",
          name: "Lookup",
          code: "def lookup():\n    return 'ok'",
          packages: "requests",
          args: [],
        },
      },
    ]);

    expect(result.edges).toEqual([
      {
        id: "edge-1",
        source: "agent-1",
        target: "tool-1",
        data: { edgeType: "tool_access" },
      },
    ]);
  });

  it("round-trips defaulted fields through encode and decode", () => {
    const encoded = encodeCanvasGraph({
      canvasName: "Round Trip Canvas",
      nodes: [
        {
          id: "agent-1",
          type: "agent",
          position: { x: 1, y: 2 },
          data: {
            id: "agent-1",
            name: "Agent",
            role: "",
            instructions: "",
            modelName: "ollama:llama3.1",
            agentType: "worker",
          },
        },
      ],
      edges: [],
    });

    const decoded = decodeCanvasResponse({
      id: "canvas-1",
      name: encoded.name,
      created_at: "2026-06-17T00:00:00Z",
      updated_at: "2026-06-17T00:00:00Z",
      nodes: {
        agents: encoded.nodes.agents.map((agent) => ({
          ...agent,
          canvas_id: "canvas-1",
        })),
        tools: [],
      },
      edges: [],
    });

    expect(decoded.nodes[0]).toMatchObject({
      id: "agent-1",
      type: "agent",
      data: {
        name: "Agent",
        modelName: "ollama:llama3.1",
        agentType: "worker",
        enablePlotting: false,
        enableMemory: false,
        enableConversationHistory: false,
        enableRag: false,
        ragChunkSize: 1000,
      },
    });
  });
});