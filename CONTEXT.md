# Agent Builder

A visual tool for composing AI agent workflows. Users wire agents and tools together on a canvas, then execute the workflow against a live backend.

## Language

**Canvas**:
A named, persisted workspace containing a graph of nodes and edges. A user works on one Canvas at a time.
_Avoid_: Board, diagram, flow, graph, workspace

**Agent Node**:
A visual block on the Canvas representing an AI agent with a name, role, instructions, and LLM model.
_Avoid_: Agent, block, step

**Tool Node**:
A visual block on the Canvas containing user-written Python code that an Agent Node can invoke.
_Avoid_: Function node, code node, script node

**Edge**:
A directed connection between two nodes. An Agent→Tool Edge grants the agent the ability to call that tool. An Agent→Agent Edge is a handoff.
_Avoid_: Connection, link, arrow

**Handoff**:
An Agent→Agent Edge. At runtime the source agent can delegate execution to the target agent.
_Avoid_: Delegation, routing

**Implicit Orchestrator**:
A hidden top-level agent created at runtime that routes the user's prompt to the appropriate Agent Node via handoff. It is never visible on the Canvas.
_Avoid_: Root agent, top-level agent, coordinator

**Workflow**:
A Canvas at the moment of execution — the resolved combination of Agent Nodes, Tool Nodes, and Edges that the backend compiles into live agent instances.
_Avoid_: Pipeline, graph, run

**Execution Log**:
The streaming output panel that shows thoughts, tool calls, and results produced during a Workflow run.
_Avoid_: Console, output, log, terminal

## Example dialogue

> **Dev**: "Should I call it a 'flow' when the user clicks Run?"
>
> **Domain expert**: "No — the Canvas is what they built. What gets executed is a Workflow. The Canvas is always there; a Workflow only exists during a run."

> **Dev**: "The Agent Node that routes to other agents — is that the Orchestrator?"
>
> **Domain expert**: "No, the Orchestrator is implicit — the user never places it on the Canvas. What they place are Agent Nodes. Routing between them is done via Handoff Edges."
