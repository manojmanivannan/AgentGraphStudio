import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { McpToolTestPanel } from "./McpToolTestPanel";
import type { McpToolGrantData, ToolInspectResponse, ToolTestResponse } from "@/types";

vi.mock("@/lib/api", () => ({
  probeMcpTool: vi.fn(),
  callMcpTool: vi.fn(),
  inspectMcpTool: vi.fn(),
}));

import { callMcpTool, inspectMcpTool, probeMcpTool } from "@/lib/api";

const GRANTS: McpToolGrantData[] = [{ name: "add", requiresApproval: false }];

function probeOk(): ToolTestResponse {
  return {
    kind: "mcp",
    stage: "probe",
    ok: true,
    success: true,
    server_name: "ags-probe-ref",
    server_version: "1.0",
    tools: ["add"],
    tool_count: 1,
    latency_ms: 12,
    detail: "OK",
    classification: null,
  };
}

function probeFail(): ToolTestResponse {
  return {
    kind: "mcp",
    stage: "probe",
    ok: false,
    success: false,
    server_name: null,
    tools: [],
    tool_count: 0,
    latency_ms: 3,
    detail: "401 Unauthorized — the credential is missing, invalid, or expired.",
    classification: "connection_failure",
  };
}

function inspectAdd(): ToolInspectResponse {
  return {
    kind: "mcp",
    ok: true,
    tool: {
      name: "add",
      description: "Add two integers.",
      input_schema: {
        type: "object",
        properties: {
          a: { type: "integer", description: "First addend" },
          b: { type: "integer", description: "Second addend" },
          label: { type: "string", description: "Optional label" },
          enabled: { type: "boolean" },
        },
        required: ["a", "b"],
      },
    },
    tools: [],
    arguments: [],
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(probeMcpTool).mockResolvedValue(probeOk());
  vi.mocked(inspectMcpTool).mockResolvedValue(inspectAdd());
  vi.mocked(callMcpTool).mockResolvedValue({
    kind: "mcp",
    stage: "call",
    ok: true,
    is_error: false,
    success: true,
    blocks: [{ type: "text", text: "5", mime_type: null, resource_uri: null, placeholder: null }],
    latency_ms: 7,
    detail: "OK",
  });
});

describe("McpToolTestPanel", () => {
  it("renders the connection button and the granted tool, and probes on click", async () => {
    render(<McpToolTestPanel serverId="srv-1" serverName="Context7" tools={GRANTS} />);

    await userEvent.click(screen.getByTestId("mcp-test-connection-button"));
    await waitFor(() => expect(probeMcpTool).toHaveBeenCalledWith("srv-1", undefined));
  });

  it("after a successful probe loads the schema and renders typed argument fields", async () => {
    render(<McpToolTestPanel serverId="srv-1" serverName="Context7" tools={GRANTS} />);

    await userEvent.click(screen.getByTestId("mcp-test-connection-button"));

    const probeResult = await screen.findByTestId("mcp-test-probe-result");
    expect(probeResult.getAttribute("data-ok")).toBe("true");

    await screen.findByTestId("mcp-test-arg-a");
    // Schema-driven field types.
    const a = screen.getByTestId("mcp-test-arg-a") as HTMLInputElement;
    expect(a.type).toBe("number");
    const label = screen.getByTestId("mcp-test-arg-label") as HTMLInputElement;
    expect(label.type).toBe("text");
    const enabled = screen.getByTestId("mcp-test-arg-enabled");
    expect(enabled.tagName).toBe("INPUT");
    expect((enabled as HTMLInputElement).type).toBe("checkbox");

    // Run button appears once args are ready.
    expect(screen.getByTestId("mcp-test-run-button")).toBeInTheDocument();
    expect(inspectMcpTool).toHaveBeenCalledWith("srv-1", "add");
  });

  it("a failed probe shows the structured error and never reaches the call stage", async () => {
    vi.mocked(probeMcpTool).mockResolvedValue(probeFail());

    render(<McpToolTestPanel serverId="srv-1" serverName="Context7" tools={GRANTS} />);
    await userEvent.click(screen.getByTestId("mcp-test-connection-button"));

    const probeResult = await screen.findByTestId("mcp-test-probe-result");
    expect(probeResult.getAttribute("data-ok")).toBe("false");
    expect(probeResult.textContent).toContain("401 Unauthorized");

    expect(screen.queryByTestId("mcp-test-run-button")).not.toBeInTheDocument();
    expect(inspectMcpTool).not.toHaveBeenCalled();
  });

  it("runs the remote call with coerced schema-driven args", async () => {
    render(<McpToolTestPanel serverId="srv-1" serverName="Context7" tools={GRANTS} />);
    await userEvent.click(screen.getByTestId("mcp-test-connection-button"));
    await screen.findByTestId("mcp-test-arg-a");

    await userEvent.type(screen.getByTestId("mcp-test-arg-a"), "2");
    await userEvent.type(screen.getByTestId("mcp-test-arg-b"), "3");
    await userEvent.click(screen.getByTestId("mcp-test-run-button"));

    await waitFor(() =>
      expect(callMcpTool).toHaveBeenCalledWith(
        "srv-1",
        "add",
        // Integer fields are coerced to numbers; the untouched optional
        // string field is omitted entirely.
        { a: 2, b: 3, enabled: false },
        undefined
      )
    );

    const result = await screen.findByTestId("mcp-test-result");
    expect(result.getAttribute("data-status")).toBe("success");
    expect(result.textContent).toContain("5");
  });

  it("renders an in-band isError result as an error, not a success", async () => {
    vi.mocked(callMcpTool).mockResolvedValue({
      kind: "mcp",
      stage: "call",
      ok: true,
      is_error: true,
      success: false,
      blocks: [
        { type: "text", text: "boom — in-band failure", mime_type: null, resource_uri: null, placeholder: null },
      ],
      latency_ms: 5,
      detail: "OK",
    });

    render(<McpToolTestPanel serverId="srv-1" serverName="Context7" tools={GRANTS} />);
    await userEvent.click(screen.getByTestId("mcp-test-connection-button"));
    await screen.findByTestId("mcp-test-arg-a");
    await userEvent.click(screen.getByTestId("mcp-test-run-button"));

    const result = await screen.findByTestId("mcp-test-result");
    expect(result.getAttribute("data-status")).toBe("error");
    expect(result.textContent).toContain("boom — in-band failure");
  });

  it("renders a call-level failure (unreachable server) as a structured error", async () => {
    vi.mocked(callMcpTool).mockResolvedValue({
      kind: "mcp",
      stage: "call",
      ok: false,
      is_error: false,
      success: false,
      blocks: [],
      latency_ms: 2,
      detail: "Connection refused.",
      classification: "connection_failure",
    });

    render(<McpToolTestPanel serverId="srv-1" serverName="Context7" tools={GRANTS} />);
    await userEvent.click(screen.getByTestId("mcp-test-connection-button"));
    await screen.findByTestId("mcp-test-arg-a");
    await userEvent.click(screen.getByTestId("mcp-test-run-button"));

    const result = await screen.findByTestId("mcp-test-result");
    expect(result.getAttribute("data-status")).toBe("error");
    expect(result.textContent).toContain("Connection refused.");
  });

  it("sends the credential override (masked field) with both stages", async () => {
    render(<McpToolTestPanel serverId="srv-1" serverName="Context7" tools={GRANTS} />);

    const credential = screen.getByTestId("mcp-test-credential") as HTMLInputElement;
    expect(credential.type).toBe("password");
    expect(credential.placeholder).toContain("••");
    await userEvent.type(credential, "Bearer token-1");

    await userEvent.click(screen.getByTestId("mcp-test-connection-button"));
    await waitFor(() => expect(probeMcpTool).toHaveBeenCalledWith("srv-1", "Bearer token-1"));

    await screen.findByTestId("mcp-test-arg-a");
    await userEvent.type(screen.getByTestId("mcp-test-arg-a"), "2");
    await userEvent.type(screen.getByTestId("mcp-test-arg-b"), "3");
    await userEvent.click(screen.getByTestId("mcp-test-run-button"));
    await waitFor(() =>
      expect(callMcpTool).toHaveBeenCalledWith("srv-1", "add", expect.anything(), "Bearer token-1")
    );
  });

  it("selects between multiple granted tools and re-loads the schema on switch", async () => {
    const twoTools: McpToolGrantData[] = [
      { name: "add", requiresApproval: false },
      { name: "explode", requiresApproval: true },
    ];
    render(<McpToolTestPanel serverId="srv-1" serverName="Context7" tools={twoTools} />);

    await userEvent.click(screen.getByTestId("mcp-test-connection-button"));
    await screen.findByTestId("mcp-test-arg-a");
    expect(inspectMcpTool).toHaveBeenCalledWith("srv-1", "add");

    fireEvent.change(screen.getByTestId("mcp-test-tool-select"), {
      target: { value: "explode" },
    });
    await waitFor(() =>
      expect(inspectMcpTool).toHaveBeenCalledWith("srv-1", "explode")
    );
  });
});