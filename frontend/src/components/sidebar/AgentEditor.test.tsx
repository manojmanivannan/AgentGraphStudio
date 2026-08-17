import { beforeEach, describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { useCanvasStore } from "@/store/canvasStore";
import { server } from "@/test/mocks/server";
import { AgentEditor } from "./AgentEditor";
import type { Node } from "@xyflow/react";

const API = "http://localhost:8000/api";

const agentNode: Node = {
  id: "agent-1",
  type: "agent",
  position: { x: 0, y: 0 },
  data: {
    id: "agent-1",
    name: "Researcher",
    role: "Researches topics",
    instructions: "Be thorough",
    modelName: "ollama:llama3.1",
    agentType: "worker",
  },
};

beforeEach(() => {
  useCanvasStore.getState().reset();
  server.resetHandlers();
});

describe("AgentEditor", () => {
  it("shows placeholder when no agent node is selected", () => {
    render(<AgentEditor />);
    expect(
      screen.getByText("Select an agent node to edit its properties")
    ).toBeInTheDocument();
  });

  it("renders all fields for a selected agent node", () => {
    useCanvasStore.getState().setNodes([agentNode]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    expect(screen.getByTestId("agent-name-input")).toHaveValue("Researcher");
    expect(screen.getByTestId("agent-role-input")).toHaveValue("Researches topics");
    expect(screen.getByTestId("agent-instructions-input")).toHaveValue("Be thorough");
    expect(screen.getByTestId("agent-type-select")).toHaveValue("worker");
  });

  it("updates the name field in the store when typed", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setNodes([agentNode]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    await user.clear(screen.getByTestId("agent-name-input"));
    await user.type(screen.getByTestId("agent-name-input"), "NewName");

    const stored = useCanvasStore.getState().nodes.find((n) => n.id === "agent-1");
    expect(stored?.data.name).toBe("NewName");
  });

  it("updates the agentType when the type select is changed", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setNodes([agentNode]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    await user.selectOptions(screen.getByTestId("agent-type-select"), "router");

    const stored = useCanvasStore.getState().nodes.find((n) => n.id === "agent-1");
    expect(stored?.data.agentType).toBe("router");
  });

  it("updates the role field in the store", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setNodes([agentNode]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    await user.clear(screen.getByTestId("agent-role-input"));
    await user.type(screen.getByTestId("agent-role-input"), "New Role");

    const stored = useCanvasStore.getState().nodes.find((n) => n.id === "agent-1");
    expect(stored?.data.role).toBe("New Role");
  });

  it("updates the instructions field in the store", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setNodes([agentNode]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    await user.clear(screen.getByTestId("agent-instructions-input"));
    await user.type(screen.getByTestId("agent-instructions-input"), "New instructions");

    const stored = useCanvasStore.getState().nodes.find((n) => n.id === "agent-1");
    expect(stored?.data.instructions).toBe("New instructions");
  });

  it("shows memory toggle for worker agents", () => {
    useCanvasStore.getState().setNodes([agentNode]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    expect(screen.getByTestId("agent-enable-memory")).toBeInTheDocument();
  });

  it("shows memory toggle for router agents", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setNodes([agentNode]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    await user.selectOptions(screen.getByTestId("agent-type-select"), "router");

    expect(screen.getByTestId("agent-enable-memory")).toBeInTheDocument();
  });

  it("shows history toggle only for router agents", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setNodes([agentNode]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    // Worker: history toggle should not be visible
    expect(screen.queryByTestId("agent-enable-history")).not.toBeInTheDocument();

    // Switch to router: history toggle should appear
    await user.selectOptions(screen.getByTestId("agent-type-select"), "router");

    expect(screen.getByTestId("agent-enable-history")).toBeInTheDocument();
  });

  it("memory toggle updates store", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setNodes([agentNode]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    await user.click(screen.getByTestId("agent-enable-memory"));

    const stored = useCanvasStore.getState().nodes.find((n) => n.id === "agent-1");
    expect(stored?.data.enableMemory).toBe(true);
  });

  it("shows plotting toggle for worker agents", () => {
    useCanvasStore.getState().setNodes([agentNode]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    expect(screen.getByTestId("agent-enable-plotting")).toBeInTheDocument();
  });

  it("does not show plotting toggle for router agents", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setNodes([agentNode]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    // Worker: plotting toggle should be visible
    expect(screen.getByTestId("agent-enable-plotting")).toBeInTheDocument();

    // Switch to router: plotting toggle should disappear
    await user.selectOptions(screen.getByTestId("agent-type-select"), "router");

    expect(screen.queryByTestId("agent-enable-plotting")).not.toBeInTheDocument();
  });

  it("resets enablePlotting to false when agentType is changed to router", async () => {
    const user = userEvent.setup();
    const withPlotting = {
      ...agentNode,
      data: { ...agentNode.data, enablePlotting: true }
    };
    useCanvasStore.getState().setNodes([withPlotting]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    await user.selectOptions(screen.getByTestId("agent-type-select"), "router");

    const stored = useCanvasStore.getState().nodes.find((n) => n.id === "agent-1");
    expect(stored?.data.enablePlotting).toBe(false);
  });

  it("plotting toggle updates store", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setNodes([agentNode]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    await user.click(screen.getByTestId("agent-enable-plotting"));

    const stored = useCanvasStore.getState().nodes.find((n) => n.id === "agent-1");
    expect(stored?.data.enablePlotting).toBe(true);
  });

  it("shows coding toggle for worker agents", () => {
    useCanvasStore.getState().setNodes([agentNode]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    expect(screen.getByTestId("agent-enable-coding")).toBeInTheDocument();
  });

  it("does not show coding toggle for router agents", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setNodes([agentNode]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    expect(screen.getByTestId("agent-enable-coding")).toBeInTheDocument();

    await user.selectOptions(screen.getByTestId("agent-type-select"), "router");

    expect(screen.queryByTestId("agent-enable-coding")).not.toBeInTheDocument();
  });

  it("resets enableCoding to false when agentType is changed to router", async () => {
    const user = userEvent.setup();
    const withCoding = {
      ...agentNode,
      data: { ...agentNode.data, enableCoding: true }
    };
    useCanvasStore.getState().setNodes([withCoding]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    await user.selectOptions(screen.getByTestId("agent-type-select"), "router");

    const stored = useCanvasStore.getState().nodes.find((n) => n.id === "agent-1");
    expect(stored?.data.enableCoding).toBe(false);
  });

  it("coding toggle updates store", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setNodes([agentNode]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    await user.click(screen.getByTestId("agent-enable-coding"));

    const stored = useCanvasStore.getState().nodes.find((n) => n.id === "agent-1");
    expect(stored?.data.enableCoding).toBe(true);
  });

  it("shows network toggle for worker agents", () => {
    useCanvasStore.getState().setNodes([agentNode]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    expect(screen.getByTestId("agent-enable-network")).toBeInTheDocument();
  });

  it("does not show network toggle for router agents", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setNodes([agentNode]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    expect(screen.getByTestId("agent-enable-network")).toBeInTheDocument();

    await user.selectOptions(screen.getByTestId("agent-type-select"), "router");

    expect(screen.queryByTestId("agent-enable-network")).not.toBeInTheDocument();
  });

  it("resets enableNetwork to false when agentType is changed to router", async () => {
    const user = userEvent.setup();
    const withNetwork = {
      ...agentNode,
      data: { ...agentNode.data, enableNetwork: true }
    };
    useCanvasStore.getState().setNodes([withNetwork]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    await user.selectOptions(screen.getByTestId("agent-type-select"), "router");

    const stored = useCanvasStore.getState().nodes.find((n) => n.id === "agent-1");
    expect(stored?.data.enableNetwork).toBe(false);
  });

  it("network toggle updates store", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setNodes([agentNode]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    await user.click(screen.getByTestId("agent-enable-network"));

    const stored = useCanvasStore.getState().nodes.find((n) => n.id === "agent-1");
    expect(stored?.data.enableNetwork).toBe(true);
  });

  it("history toggle updates store for router agents", async () => {
    const user = userEvent.setup();
    const routerNode = { ...agentNode, data: { ...agentNode.data, agentType: "router" } };
    useCanvasStore.getState().setNodes([routerNode]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    await user.click(screen.getByTestId("agent-enable-history"));

    const stored = useCanvasStore.getState().nodes.find((n) => n.id === "agent-1");
    expect(stored?.data.enableConversationHistory).toBe(true);
  });

  it("shows RAG toggle for worker agents", () => {
    useCanvasStore.getState().setNodes([agentNode]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    expect(screen.getByTestId("agent-enable-rag")).toBeInTheDocument();
  });

  it("does not show RAG toggle for router agents", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setNodes([agentNode]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    await user.selectOptions(screen.getByTestId("agent-type-select"), "router");

    expect(screen.queryByTestId("agent-enable-rag")).not.toBeInTheDocument();
  });

  it("RAG toggle updates store", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setNodes([agentNode]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    await user.click(screen.getByTestId("agent-enable-rag"));

    const stored = useCanvasStore.getState().nodes.find((n) => n.id === "agent-1");
    expect(stored?.data.enableRag).toBe(true);
  });

  it("shows RAG chunk size and documents section when RAG is enabled", async () => {
    const user = userEvent.setup();
    const ragNode = {
      ...agentNode,
      data: { ...agentNode.data, enableRag: true, ragChunkSize: 500 },
    };
    useCanvasStore.getState().setNodes([ragNode]);
    useCanvasStore.getState().selectNode("agent-1");

    server.use(
      http.get(`${API}/canvases//agents/agent-1/documents`, () =>
        HttpResponse.json([])
      )
    );

    render(<AgentEditor />);

    await waitFor(() => {
      expect(screen.getByText("Chunk Size (tokens)")).toBeInTheDocument();
      expect(screen.getByText("Documents")).toBeInTheDocument();
      expect(screen.getByText("Upload File")).toBeInTheDocument();
    });
  });

  it("shows connected tools when edges exist", () => {
    const toolNode: Node = {
      id: "tool-1",
      type: "tool",
      position: { x: 300, y: 0 },
      data: { id: "tool-1", name: "My Tool", code: "def run(): pass" },
    };

    useCanvasStore.getState().setNodes([agentNode, toolNode]);
    useCanvasStore.getState().setEdges([
      {
        id: "edge-1",
        source: "agent-1",
        target: "tool-1",
        data: { edgeType: "tool_access" },
      },
    ]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    expect(screen.getByText("Connected Tools")).toBeInTheDocument();
    expect(screen.getByText("My Tool")).toBeInTheDocument();
  });

  it("shows 'No tools connected' when no edges exist", () => {
    useCanvasStore.getState().setNodes([agentNode]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    expect(screen.getByText("No tools connected")).toBeInTheDocument();
  });

  it("renders Capabilities section header", () => {
    useCanvasStore.getState().setNodes([agentNode]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    expect(screen.getByText("Capabilities")).toBeInTheDocument();
  });

  it("shows instructions info tooltip for worker agents", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setNodes([agentNode]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    const infoButton = screen.getByTestId("agent-instructions-info");
    await user.hover(infoButton);

    expect(
      screen.getByText(/In order to use rag context, use \{\{ rag_document \}\}/)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/top 5 results/)
    ).toBeInTheDocument();
  });

  it("does not show instructions info tooltip for router agents", () => {
    const routerNode = { ...agentNode, data: { ...agentNode.data, agentType: "router" } };
    useCanvasStore.getState().setNodes([routerNode]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    expect(screen.queryByTestId("agent-instructions-info")).not.toBeInTheDocument();
  });
});
