# Agent Builder

A visual tool for composing AI agent workflows. Users wire agents and tools together on a canvas, then execute the workflow against a live backend.

## Language

**Canvas**:
A named, persisted workspace containing a graph of nodes and edges. A user works on one Canvas at a time.
_Avoid_: Board, diagram, flow, graph, workspace

**Agent Node**:
A visual block on the Canvas representing an AI agent with a name, role, instructions, LLM model, and agent type (worker or router).
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

**Worker**:
An agent type that executes tasks by reasoning through DSPy ReAct (thought → tool call → observation loops). Workers can call tools but cannot hand off to other agents.
_Avoid_: Sub-agent, leaf agent

**Router**:
An agent type that orchestrates by handing off tasks to other agents (workers or other routers). Routers are built lazily at run time when first invoked.
_Avoid_: Orchestrator, coordinator, manager

**StreamingReAct**:
A DSPy ReAct subclass (in `streaming_react.py`) that emits events at each ReAct iteration (thought, tool_start, tool_result). Note: there is no `agent_start` event emitted here — that comes from the runner.
_Avoid_: Custom agent, React agent

**Conversation**:
A persisted chat thread scoped to a Canvas. Tracks multi-turn user↔assistant exchanges. Messages include role, agent name, node_id, and event_type.
_Avoid_: Thread, chat session

**Turn**:
A single user message + the resulting assistant messages (steps + final answer) within a Conversation.
_Avoid_: Exchange, round

**Workflow**:
A Canvas at the moment of execution — the resolved combination of Agent Nodes, Tool Nodes, and Edges that the backend compiles into live DSPy agent instances.
_Avoid_: Pipeline, graph, run

**Execution Event**:
A JSON message streamed over WebSocket during a Workflow run. Types: run_start, agent_start, thought, tool_start, tool_result, handoff, final_answer, run_complete, error.
_Avoid_: Console, output, log, terminal

**Memory**:
Per-agent long-term storage backed by mem0 + Qdrant vector store. Each agent optionally gets three memory tools: `memory_search`, `memory_store`, `memory_get_all`.
_Avoid_: Long-term memory, storage

**Observability**:
An embedded MLflow UI iframe for tracing DSPy agent calls, tool invocations, and LLM interactions via `mlflow.dspy.autolog()`.
_Avoid_: Tracing, monitoring, dashboard

**Sandbox**:
A Deno/Pyodide subprocess (via DSPy `PythonInterpreter`) that executes all tool code in an isolated WASM-based Python runtime. No access to host filesystem, network, or environment variables by default. Managed as a singleton by `canvas_server.sandbox.Sandbox`.
_Avoid_: Container, VM, isolation layer

**Tool Inspection**:
Extracting function metadata (name, parameter names, type hints, default values) from user-written Python code. Used by the Test Tool UI to generate argument input fields. Provided by `POST /api/tools/inspect`.
_Avoid_: Reflection, introspection, parsing

**Tool Test**:
Running a tool function in the sandbox with user-provided argument values and returning the result (output or error) to the UI. Provided by `POST /api/tools/test`.
_Avoid_: Playground, REPL, runner