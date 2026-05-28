import { beforeEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useCanvasStore } from "@/store/canvasStore";
import { AgentEditor } from "./AgentEditor";
import type { Node } from "@xyflow/react";

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
    expect(screen.getByTestId("agent-model-input")).toHaveValue("ollama:llama3.1");
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

  it("updates the model field in the store", async () => {
    const user = userEvent.setup();
    useCanvasStore.getState().setNodes([agentNode]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    await user.clear(screen.getByTestId("agent-model-input"));
    await user.type(screen.getByTestId("agent-model-input"), "openai:gpt-4o");

    const stored = useCanvasStore.getState().nodes.find((n) => n.id === "agent-1");
    expect(stored?.data.modelName).toBe("openai:gpt-4o");
  });

  it("has a datalist with model suggestions", () => {
    useCanvasStore.getState().setNodes([agentNode]);
    useCanvasStore.getState().selectNode("agent-1");
    render(<AgentEditor />);

    expect(document.getElementById("model-suggestions")).toBeInTheDocument();
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
});
