import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Node } from "@xyflow/react";
import { McpToolPicker } from "./McpToolPicker";
import { useCanvasStore } from "@/store/canvasStore";
import { useSettingsModalStore } from "@/store/settingsModalStore";
import type { McpServer, McpServerCatalog } from "@/types";

vi.mock("@/lib/api", () => ({
  listMcpServers: vi.fn(),
  fetchMcpServerCatalog: vi.fn(),
}));

import {
  fetchMcpServerCatalog,
  listMcpServers,
} from "@/lib/api";

const SERVERS: McpServer[] = [
  {
    id: "srv-1",
    name: "Context7",
    url: "https://mcp.context7.com/mcp",
    credential_header: "Authorization",
    credential_set: true,
    credential_preview: null,
    url_warning: null,
  },
  {
    id: "srv-2",
    name: "DocsServer",
    url: "https://docs.example.com/mcp",
    credential_header: null,
    credential_set: false,
    credential_preview: null,
    url_warning: null,
  },
];

function catalog(
  tools: Array<{
    name: string;
    description?: string;
    input_schema?: Record<string, unknown>;
  }>
): McpServerCatalog {
  return {
    ok: true,
    server_id: "srv-1",
    tools: tools.map((t) => ({
      name: t.name,
      description: t.description ?? null,
      input_schema: t.input_schema ?? { type: "object", properties: {} },
    })),
    server_name: "ags-probe-ref",
    server_version: "1.0",
    latency_ms: 4,
    detail: "OK",
    classification: null,
    protocol_revision: "2025-06-18",
  };
}

function nodeWith(data: Partial<Node["data"]> = {}): Node {
  return {
    id: "tool-1",
    type: "tool",
    position: { x: 0, y: 0 },
    data: {
      id: "tool-1",
      name: "Search Tools",
      code: "",
      mcpServerId: "srv-1",
      mcpTools: [],
      mcpSeenTools: [],
      ...data,
    },
  };
}

function nodeData() {
  const nodes = useCanvasStore.getState().nodes;
  return nodes.find((n) => n.id === "tool-1")!.data as Record<string, unknown>;
}

beforeEach(() => {
  useCanvasStore.getState().reset();
  useSettingsModalStore.getState().reset();
  vi.clearAllMocks();
  vi.mocked(listMcpServers).mockResolvedValue(SERVERS);
  vi.mocked(fetchMcpServerCatalog).mockResolvedValue(catalog([]));
  useCanvasStore.getState().setNodes([nodeWith()]);
  useCanvasStore.getState().selectNode("tool-1");
});

describe("McpToolPicker", () => {
  it("renders the server chip with name and endpoint and the checklist from a live fetch", async () => {
    vi.mocked(fetchMcpServerCatalog).mockResolvedValue(
      catalog([
        { name: "web_search", description: "Search the web for pages." },
        { name: "read_doc", description: "Read a documentation page." },
      ])
    );

    render(<McpToolPicker nodeId="tool-1" />);

    // Server chip: registration name + endpoint (from the registry, not the node).
    const chip = await screen.findByTestId("mcp-server-chip");
    expect(within(chip).getByText("Context7")).toBeInTheDocument();
    expect(within(chip).getByText("https://mcp.context7.com/mcp")).toBeInTheDocument();

    // Checklist header counts the live catalog.
    expect(
      await screen.findByText(/Server Tools \(2\)/)
    ).toBeInTheDocument();
    expect(screen.getByTestId("mcp-tool-row-web_search")).toBeInTheDocument();
    expect(screen.getByTestId("mcp-tool-row-read_doc")).toBeInTheDocument();
    // Exactly one catalog fetch — live read, no memoization.
    expect(fetchMcpServerCatalog).toHaveBeenCalledTimes(1);
    expect(fetchMcpServerCatalog).toHaveBeenCalledWith("srv-1");
  });

  it("enabling a tool writes a grant with requires_approval true by default", async () => {
    vi.mocked(fetchMcpServerCatalog).mockResolvedValue(
      catalog([{ name: "web_search", description: "Search." }])
    );

    render(<McpToolPicker nodeId="tool-1" />);
    await screen.findByTestId("mcp-tool-row-web_search");

    fireEvent.click(screen.getByTestId("mcp-enable-web_search"));

    await waitFor(() => {
      expect(nodeData().mcpTools).toEqual([
        { name: "web_search", requiresApproval: true },
      ]);
    });
  });

  it("shows the approval toggle on enabled rows and per-tool toggling works", async () => {
    vi.mocked(fetchMcpServerCatalog).mockResolvedValue(
      catalog([
        { name: "web_search", description: "Search." },
        { name: "read_doc", description: "Read." },
      ])
    );
    useCanvasStore.getState().setNodes([
      nodeWith({
        mcpTools: [
          { name: "web_search", requiresApproval: true },
          { name: "read_doc", requiresApproval: false },
        ],
        mcpSeenTools: ["web_search", "read_doc"],
      }),
    ]);

    render(<McpToolPicker nodeId="tool-1" />);
    await screen.findByTestId("mcp-tool-row-read_doc");

    // Approval toggle only on enabled rows.
    expect(screen.queryByTestId("mcp-approval-web_search")).toBeInTheDocument();
    expect(screen.getByTestId("mcp-approval-web_search")).toBeChecked();
    expect(screen.queryByTestId("mcp-approval-read_doc")).toBeInTheDocument();
    expect(screen.getByTestId("mcp-approval-read_doc")).not.toBeChecked();

    fireEvent.click(screen.getByTestId("mcp-approval-read_doc"));
    await waitFor(() => {
      expect(nodeData().mcpTools).toEqual([
        { name: "web_search", requiresApproval: true },
        { name: "read_doc", requiresApproval: true },
      ]);
    });

    // Disabling a tool removes its grant entirely.
    fireEvent.click(screen.getByTestId("mcp-enable-web_search"));
    await waitFor(() => {
      expect(nodeData().mcpTools).toEqual([
        { name: "read_doc", requiresApproval: true },
      ]);
    });
  });

  it("filters the checklist with the filter box", async () => {
    vi.mocked(fetchMcpServerCatalog).mockResolvedValue(
      catalog([
        { name: "web_search", description: "Search the web." },
        { name: "read_doc", description: "Read docs." },
      ])
    );

    render(<McpToolPicker nodeId="tool-1" />);
    await screen.findByTestId("mcp-tool-row-read_doc");

    const filter = screen.getByTestId("mcp-filter");
    await userEvent.type(filter, "web");

    expect(screen.getByTestId("mcp-tool-row-web_search")).toBeInTheDocument();
    expect(screen.queryByTestId("mcp-tool-row-read_doc")).not.toBeInTheDocument();
  });

  it("expands the server-provided input schema from catalog data", async () => {
    vi.mocked(fetchMcpServerCatalog).mockResolvedValue(
      catalog([
        {
          name: "web_search",
          description: "Search.",
          input_schema: {
            type: "object",
            properties: { query: { type: "string" } },
            required: ["query"],
          },
        },
      ])
    );

    render(<McpToolPicker nodeId="tool-1" />);
    await screen.findByTestId("mcp-tool-row-web_search");

    expect(screen.queryByTestId("mcp-schema-web_search")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("mcp-schema-toggle-web_search"));

    const schema = screen.getByTestId("mcp-schema-web_search");
    expect(schema.textContent).toContain('"query"');
    expect(schema.textContent).toContain('"string"');
  });

  it("marks catalog tools absent from the enablement history with a NEW badge and records the history", async () => {
    vi.mocked(fetchMcpServerCatalog).mockResolvedValue(
      catalog([
        { name: "web_search", description: "Search." },
        { name: "read_doc", description: "Read." },
      ])
    );
    // web_search was seen before; read_doc has never been shown.
    useCanvasStore.getState().setNodes([nodeWith({ mcpSeenTools: ["web_search"] })]);

    render(<McpToolPicker nodeId="tool-1" />);
    await screen.findByTestId("mcp-tool-row-read_doc");

    // web_search was seen before; only read_doc (never shown) is NEW.
    expect(screen.queryByTestId("mcp-new-badge-web_search")).not.toBeInTheDocument();
    expect(screen.getByTestId("mcp-new-badge-read_doc")).toBeInTheDocument();

    // The viewed catalog names are recorded into the node's history —
    // names only, never a catalog snapshot.
    await waitFor(() => {
      expect(nodeData().mcpSeenTools).toEqual(["web_search", "read_doc"]);
    });
  });

  it("flags enabled-but-vanished tools in an excluded block with a Drop affordance", async () => {
    vi.mocked(fetchMcpServerCatalog).mockResolvedValue(
      catalog([{ name: "web_search", description: "Search." }])
    );
    useCanvasStore.getState().setNodes([
      nodeWith({
        mcpTools: [
          { name: "web_search", requiresApproval: true },
          { name: "ghost_tool", requiresApproval: false },
        ],
        mcpSeenTools: ["web_search", "ghost_tool"],
      }),
    ]);

    render(<McpToolPicker nodeId="tool-1" />);
    await screen.findByTestId("mcp-tool-row-web_search");

    const block = screen.getByTestId("mcp-excluded-block");
    expect(within(block).getByText("ghost_tool")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("mcp-drop-ghost_tool"));
    await waitFor(() => {
      expect(nodeData().mcpTools).toEqual([
        { name: "web_search", requiresApproval: true },
      ]);
    });
  });

  it("re-fetches live on Refresh and re-diffs", async () => {
    const first = catalog([{ name: "web_search", description: "Search." }]);
    const second = catalog([
      { name: "web_search", description: "Search." },
      { name: "doc_search", description: "Search docs." },
    ]);
    vi.mocked(fetchMcpServerCatalog)
      .mockResolvedValueOnce(first)
      .mockResolvedValueOnce(second);

    render(<McpToolPicker nodeId="tool-1" />);
    await screen.findByTestId("mcp-tool-row-web_search");
    expect(screen.queryByTestId("mcp-tool-row-doc_search")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("mcp-refresh"));

    expect(await screen.findByTestId("mcp-tool-row-doc_search")).toBeInTheDocument();
    expect(fetchMcpServerCatalog).toHaveBeenCalledTimes(2);
  });

  it("shows an honest error with Retry on an unreachable server and never stale tools", async () => {
    vi.mocked(fetchMcpServerCatalog).mockRejectedValue(
      new Error("Request failed with status 404")
    );

    render(<McpToolPicker nodeId="tool-1" />);
    const error = await screen.findByTestId("mcp-catalog-error");
    expect(error.textContent).toContain("404");
    expect(screen.queryByTestId("mcp-tools-list")).not.toBeInTheDocument();

    // Recover: Retry re-fetches and shows the checklist.
    vi.mocked(fetchMcpServerCatalog).mockResolvedValue(
      catalog([{ name: "web_search", description: "Search." }])
    );
    fireEvent.click(screen.getByTestId("mcp-retry"));
    expect(await screen.findByTestId("mcp-tools-list")).toBeInTheDocument();
  });

  it("reopens the registered-servers picker from the chip and selecting a server resets the selection", async () => {
    vi.mocked(fetchMcpServerCatalog).mockResolvedValue(
      catalog([{ name: "web_search", description: "Search." }])
    );
    useCanvasStore.getState().setNodes([
      nodeWith({
        mcpTools: [{ name: "web_search", requiresApproval: true }],
        mcpSeenTools: ["web_search"],
      }),
    ]);

    render(<McpToolPicker nodeId="tool-1" />);
    await screen.findByTestId("mcp-tool-row-web_search");

    fireEvent.click(screen.getByTestId("mcp-server-chip"));
    const picker = await screen.findByTestId("mcp-server-picker");
    expect(within(picker).getByText("DocsServer")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("mcp-select-server-DocsServer"));

    await waitFor(() => {
      expect(nodeData().mcpServerId).toBe("srv-2");
      // Switching servers resets the tool selection — the old grant belongs
      // to a different server.
      expect(nodeData().mcpTools).toEqual([]);
    });
    // The new server's catalog is fetched live.
    await waitFor(() => {
      expect(fetchMcpServerCatalog).toHaveBeenCalledWith("srv-2");
    });
  });

  it("opens Settings on the MCP Servers section via the Manage servers link", async () => {
    render(<McpToolPicker nodeId="tool-1" />);

    fireEvent.click(await screen.findByTestId("mcp-manage-servers"));

    const state = useSettingsModalStore.getState();
    expect(state.open).toBe(true);
    expect(state.section).toBe("mcp-servers");
  });

  it("offers an attach affordance for a node with no server and attaches on selection", async () => {
    useCanvasStore
      .getState()
      .setNodes([nodeWith({ mcpServerId: null, mcpTools: [], code: "def add(a, b): pass" })]);
    vi.mocked(fetchMcpServerCatalog).mockResolvedValue(
      catalog([{ name: "web_search", description: "Search." }])
    );

    render(<McpToolPicker nodeId="tool-1" />);

    expect(screen.queryByTestId("mcp-server-chip")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("mcp-attach-server"));
    fireEvent.click(
      await screen.findByTestId("mcp-select-server-Context7")
    );

    await waitFor(() => {
      expect(nodeData().mcpServerId).toBe("srv-1");
      // Attaching a server makes the node MCP-backed: code stays empty.
      expect(nodeData().code).toBe("");
    });
    expect(await screen.findByTestId("mcp-server-chip")).toBeInTheDocument();
  });

  it("shows an unknown-server error state when the granted server vanished from the registry", async () => {
    useCanvasStore.getState().setNodes([
      nodeWith({
        mcpServerId: "srv-gone",
        mcpTools: [{ name: "web_search", requiresApproval: true }],
      }),
    ]);

    render(<McpToolPicker nodeId="tool-1" />);

    const error = await screen.findByTestId("mcp-catalog-error");
    expect(error.textContent).toContain("no longer registered");
  });
});