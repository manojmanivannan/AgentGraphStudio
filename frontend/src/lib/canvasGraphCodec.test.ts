import { describe, expect, it } from "vitest";

import type { CanvasResponse } from "@/types";
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
            enable_coding: false,
            enable_network: false,
            enable_hitl: false,
            enable_memory: false,
            enable_conversation_history: false,
            enable_rag: false,
            rag_chunk_size: 1000,
            rag_top_k: 5,
            is_entry_point: false,
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
            requires_approval: false,
            mcp_server_id: null,
            mcp_tools: [],
            position_x: 30,
            position_y: 40,
          },
        ],
        attachments: [],
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
            enable_coding: false,
            enable_network: true,
            enable_memory: true,
            enable_conversation_history: true,
            enable_rag: true,
            rag_chunk_size: 2048,
            rag_top_k: 5,
            is_entry_point: true,
            enable_hitl: true,
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
            requires_approval: true,
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
          enableCoding: false,
          enableNetwork: true,
          enableMemory: true,
          enableConversationHistory: true,
          enableRag: true,
          ragChunkSize: 2048,
          ragTopK: 5,
          isEntryPoint: true,
          enableHitl: true,
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
          requiresApproval: true,
          mcpServerId: null,
          mcpTools: [],
          mcpReference: null,
        },
      },
    ]);

    expect(result.edges).toEqual([
      {
        id: "edge-1",
        source: "agent-1",
        target: "tool-1",
        sourceHandle: "tool-out",
        targetHandle: "tool-in",
        data: { edgeType: "tool_access" },
        markerEnd: {
          type: "arrowclosed",
          color: "var(--color-text-tertiary)",
        },
      },
    ]);
  });

  describe("MCP tool node grants (#132)", () => {
    it("encodes an MCP grant into the save payload", () => {
      const result = encodeCanvasGraph({
        canvasName: "MCP Canvas",
        nodes: [
          {
            id: "tool-1",
            type: "tool",
            position: { x: 0, y: 0 },
            data: {
              id: "tool-1",
              name: "Search Tools",
              code: "",
              mcpServerId: "srv-1",
              mcpTools: [
                { name: "web_search", requiresApproval: true },
                { name: "read_doc", requiresApproval: false },
              ],
            },
          },
        ],
        edges: [],
      });

      expect(result.nodes.tools).toEqual([
        {
          id: "tool-1",
          name: "Search Tools",
          code: "",
          packages: "",
          args: [],
          requires_approval: false,
          mcp_server_id: "srv-1",
          mcp_tools: [
            { name: "web_search", requires_approval: true },
            { name: "read_doc", requires_approval: false },
          ],
          position_x: 0,
          position_y: 0,
        },
      ]);
    });

    it("encodes a code tool with MCP defaults (no server, empty grant)", () => {
      const result = encodeCanvasGraph({
        canvasName: "Code Canvas",
        nodes: [
          {
            id: "tool-1",
            type: "tool",
            position: { x: 0, y: 0 },
            data: {
              id: "tool-1",
              name: "Calc",
              code: "def add(a, b): return a + b",
            },
          },
        ],
        edges: [],
      });

      expect(result.nodes.tools[0].mcp_server_id).toBeNull();
      expect(result.nodes.tools[0].mcp_tools).toEqual([]);
      expect(result.nodes.tools[0].code).toBe("def add(a, b): return a + b");
    });

    it("decodes MCP fields into tool node data", () => {
      const result = decodeCanvasResponse({
        id: "canvas-1",
        name: "MCP Canvas",
        created_at: "2026-10-11T00:00:00Z",
        updated_at: "2026-10-11T00:00:00Z",
        nodes: {
          agents: [],
          tools: [
            {
              id: "tool-1",
              canvas_id: "canvas-1",
              name: "Search Tools",
              code: "",
              packages: "",
              args: [],
              requires_approval: false,
              mcp_server_id: "srv-1",
              mcp_tools: [{ name: "web_search", requires_approval: true }],
              position_x: 1,
              position_y: 2,
            },
          ],
        },
        edges: [],
      });

      expect(result.nodes).toEqual([
        {
          id: "tool-1",
          type: "tool",
          position: { x: 1, y: 2 },
          style: { width: 220 },
          data: {
            id: "tool-1",
            name: "Search Tools",
            code: "",
            packages: "",
            args: [],
            requiresApproval: false,
            mcpServerId: "srv-1",
            mcpTools: [{ name: "web_search", requiresApproval: true }],
            mcpReference: null,
          },
        },
      ]);
    });

    it("decodes a legacy tool without MCP fields to defaults", () => {
      const result = decodeCanvasResponse({
        id: "canvas-1",
        name: "Legacy Canvas",
        created_at: "2026-10-11T00:00:00Z",
        updated_at: "2026-10-11T00:00:00Z",
        nodes: {
          agents: [],
          tools: [
            {
              id: "tool-1",
              canvas_id: "canvas-1",
              name: "Lookup",
              code: "def f(): pass",
              packages: "",
              args: [],
              requires_approval: true,
              position_x: 1,
              position_y: 2,
            },
          ],
        },
        edges: [],
      });

      const tool = result.nodes[0] as { data: Record<string, unknown> };
      expect(tool.data.mcpServerId).toBeNull();
      expect(tool.data.mcpTools).toEqual([]);
      expect(tool.data.mcpReference).toBeNull();
    });

    it("decodes an exported MCP reference into tool node data (#136)", () => {
      const reference = {
        resolved: true,
        name: "Context7",
        url: "https://mcp.context7.com/mcp",
        snapshot: {
          captured: true,
          server_name: "ctx-remote",
          server_version: "1.2.3",
          protocol_revision: "2025-11-25",
          detail: "",
          tools: [
            {
              name: "web_search",
              description: "Search the web.",
              input_schema: { type: "object", properties: {} },
            },
          ],
        },
      };
      const result = decodeCanvasResponse({
        id: "canvas-1",
        name: "Imported Canvas",
        created_at: "2026-10-11T00:00:00Z",
        updated_at: "2026-10-11T00:00:00Z",
        nodes: {
          agents: [],
          tools: [
            {
              id: "tool-1",
              canvas_id: "canvas-1",
              name: "Search Tools",
              code: "",
              packages: "",
              args: [],
              requires_approval: false,
              mcp_server_id: null,
              mcp_tools: [{ name: "web_search", requires_approval: false }],
              mcp_reference: reference as any,
              position_x: 1,
              position_y: 2,
            },
          ],
        },
        edges: [],
      });

      const tool = result.nodes[0] as unknown as {
        data: { mcpReference: typeof reference };
      };
      expect(tool.data.mcpReference).toEqual(reference);
    });

    it("round-trips an MCP grant through encode and decode", () => {
      const encoded = encodeCanvasGraph({
        canvasName: "Round Trip",
        nodes: [
          {
            id: "tool-1",
            type: "tool",
            position: { x: 0, y: 0 },
            data: {
              id: "tool-1",
              name: "Search Tools",
              code: "",
              mcpServerId: "srv-1",
              mcpTools: [{ name: "web_search", requiresApproval: true }],
            },
          },
        ],
        edges: [],
      });

      const decoded = decodeCanvasResponse({
        id: "canvas-1",
        name: "Round Trip",
        created_at: "2026-10-11T00:00:00Z",
        updated_at: "2026-10-11T00:00:00Z",
        nodes: {
          agents: [],
          tools: [
            {
              id: "tool-1",
              canvas_id: "canvas-1",
              name: encoded.nodes.tools[0].name,
              code: encoded.nodes.tools[0].code,
              packages: encoded.nodes.tools[0].packages,
              args: encoded.nodes.tools[0].args,
              requires_approval: encoded.nodes.tools[0].requires_approval,
              mcp_server_id: encoded.nodes.tools[0].mcp_server_id,
              mcp_tools: encoded.nodes.tools[0].mcp_tools,
              position_x: 0,
              position_y: 0,
            },
          ],
        },
        edges: [],
      });

      const data = decoded.nodes[0].data as {
        mcpServerId: string;
        mcpTools: { name: string; requiresApproval: boolean }[];
      };
      expect(data.mcpServerId).toBe("srv-1");
      expect(data.mcpTools).toEqual([
        { name: "web_search", requiresApproval: true },
      ]);
    });
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
        enableCoding: false,
        enableMemory: false,
        enableConversationHistory: false,
        enableRag: false,
        ragChunkSize: 1000,
        isEntryPoint: false,
        enableHitl: false,
      },
    });
  });

  it("round-trips enable_coding: true through encode and decode", () => {
    const encoded = encodeCanvasGraph({
      canvasName: "Coding RoundTrip",
      nodes: [
        {
          id: "agent-1",
          type: "agent",
          position: { x: 1, y: 2 },
          data: {
            id: "agent-1",
            name: "Coder",
            role: "",
            instructions: "",
            modelName: "ollama:llama3.1",
            agentType: "worker",
            enableCoding: true,
          },
        },
      ],
      edges: [],
    });

    // Encoded payload carries enable_coding: true.
    expect(encoded.nodes.agents[0].enable_coding).toBe(true);

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

    // Decoded store data carries enableCoding: true.
    expect(decoded.nodes[0].data.enableCoding).toBe(true);
  });

  it("round-trips enable_network: true through encode and decode", () => {
    const encoded = encodeCanvasGraph({
      canvasName: "Network RoundTrip",
      nodes: [
        {
          id: "agent-1",
          type: "agent",
          position: { x: 1, y: 2 },
          data: {
            id: "agent-1",
            name: "NetWorker",
            role: "",
            instructions: "",
            modelName: "ollama:llama3.1",
            agentType: "worker",
            enableNetwork: true,
          },
        },
      ],
      edges: [],
    });

    // Encoded payload carries enable_network: true.
    expect(encoded.nodes.agents[0].enable_network).toBe(true);

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

    // Decoded store data carries enableNetwork: true.
    expect(decoded.nodes[0].data.enableNetwork).toBe(true);
  });

  it("defaults enable_network to false when unset on encode", () => {
    const encoded = encodeCanvasGraph({
      canvasName: "Default Network",
      nodes: [
        {
          id: "agent-1",
          type: "agent",
          position: { x: 0, y: 0 },
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

    expect(encoded.nodes.agents[0].enable_network).toBe(false);
  });

  it("encodes attachment node data into a save payload", () => {
    const result = encodeCanvasGraph({
      canvasName: "Attachment Canvas",
      nodes: [
        {
          id: "att-1",
          type: "attachment",
          position: { x: 5, y: 6 },
          data: {
            id: "att-1",
            name: "Sales Data",
            fileType: "csv",
            deliveryMethod: "file_path",
            description: "Q1 sales export",
          },
        },
      ],
      edges: [],
    });

    expect(result.nodes.attachments).toEqual([
      {
        id: "att-1",
        name: "Sales Data",
        file_type: "csv",
        delivery_method: "file_path",
        description: "Q1 sales export",
        position_x: 5,
        position_y: 6,
      },
    ]);
  });

  it("defaults attachment file_type to text and description to empty string on encode", () => {
    const result = encodeCanvasGraph({
      canvasName: "Default Attachment",
      nodes: [
        {
          id: "att-1",
          type: "attachment",
          position: { x: 0, y: 0 },
          data: { id: "att-1", name: "Untyped" },
        },
      ],
      edges: [],
    });

    expect(result.nodes.attachments).toEqual([
      {
        id: "att-1",
        name: "Untyped",
        file_type: "text",
        delivery_method: "inline",
        description: "",
        position_x: 0,
        position_y: 0,
      },
    ]);
  });

  it("decodes attachment nodes from a canvas response", () => {
    const result = decodeCanvasResponse({
      id: "canvas-1",
      name: "Decoded Attachment Canvas",
      created_at: "2026-06-17T00:00:00Z",
      updated_at: "2026-06-17T00:00:00Z",
      nodes: {
        agents: [],
        tools: [],
        attachments: [
          {
            id: "att-1",
            canvas_id: "canvas-1",
            name: "Sales Data",
            file_type: "csv",
            delivery_method: "file_path",
            description: "Q1 sales export",
            position_x: 12,
            position_y: 34,
          },
        ],
      },
      edges: [],
    } as CanvasResponse);

    expect(result.nodes).toEqual([
      {
        id: "att-1",
        type: "attachment",
        position: { x: 12, y: 34 },
        style: { width: 180 },
        data: {
          id: "att-1",
          name: "Sales Data",
          fileType: "csv",
          deliveryMethod: "file_path",
          description: "Q1 sales export",
        },
      },
    ]);
  });

  it("defaults attachment deliveryMethod to inline when missing from a canvas response", () => {
    const legacyCanvas = {
      id: "canvas-1",
      name: "Decoded Attachment Canvas",
      created_at: "2026-06-17T00:00:00Z",
      updated_at: "2026-06-17T00:00:00Z",
      nodes: {
        agents: [],
        tools: [],
        attachments: [
          {
            id: "att-1",
            canvas_id: "canvas-1",
            name: "Sales Data",
            file_type: "csv",
            description: "Q1 sales export",
            position_x: 12,
            position_y: 34,
          },
        ],
      },
      edges: [],
    } as unknown as CanvasResponse;

    const result = decodeCanvasResponse(legacyCanvas);

    expect(result.nodes).toEqual([
      {
        id: "att-1",
        type: "attachment",
        position: { x: 12, y: 34 },
        style: { width: 180 },
        data: {
          id: "att-1",
          name: "Sales Data",
          fileType: "csv",
          deliveryMethod: "inline",
          description: "Q1 sales export",
        },
      },
    ]);
  });

  it("decodes produces/consumes edges into store edges", () => {
    const result = decodeCanvasResponse({
      id: "canvas-1",
      name: "Wired Canvas",
      created_at: "2026-06-17T00:00:00Z",
      updated_at: "2026-06-17T00:00:00Z",
      nodes: { agents: [], tools: [], attachments: [] },
      edges: [
        {
          id: "edge-1",
          canvas_id: "canvas-1",
          source_node_id: "agent-1",
          target_node_id: "att-1",
          edge_type: "produces",
        },
      ],
    });

    expect(result.edges).toEqual([
      {
        id: "edge-1",
        source: "agent-1",
        target: "att-1",
        sourceHandle: "attachment-out",
        targetHandle: "attachment-target",
        data: { edgeType: "produces" },
        markerEnd: {
          type: "arrowclosed",
          color: "var(--color-warning)",
        },
      },
    ]);
  });
});