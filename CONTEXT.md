# Agent Builder

A visual tool for composing AI agent workflows. Users wire agents and tools together on a canvas, then execute the workflow against a live backend.

## Language

**Canvas**:
A named, persisted workspace containing a graph of nodes and edges. A user works on one Canvas at a time.
_Avoid_: Board, diagram, flow, graph, workspace

Canvas responses use a separate response envelope from canvas save requests, so node capability fields are returned explicitly instead of being implied by the input shape.

**Agent Node**:
A visual block on the Canvas representing an AI agent with a name, role, instructions, and agent type (worker or router).
_Avoid_: Agent, block, step

**Tool Node**:
A visual block on the Canvas containing user-written Python code that an Agent Node can invoke.
_Avoid_: Function node, code node, script node

**Edge**:
A directed connection between two nodes. An Agent→Tool Edge grants the agent the ability to call that tool. An Agent→Agent Edge is a handoff.
_Avoid_: Connection, link, arrow

**Handoff**:
A directed connection between agent nodes. At runtime the source agent can delegate execution to the target agent sequentially, or concurrently in parallel if the source is a Router with multiple targets.
_Avoid_: Delegation, routing

**Worker**:
An agent type that executes tasks by reasoning through DSPy ReAct (thought → tool call → observation loops). Workers can call tools but cannot hand off to other agents.
_Avoid_: Sub-agent, leaf agent

**Router**:
An agent type that orchestrates by handing off tasks to other agents (workers or other routers). Routers are built lazily at run time when first invoked. If a Router has two or more outgoing handoff edges, it is automatically equipped with the `execute_parallel_agents` tool to invoke multiple target agents concurrently.
_Avoid_: Orchestrator, coordinator, manager

**StreamingReAct**:
A DSPy ReAct subclass (in `streaming_react.py`) that emits events at each ReAct iteration (thought, tool_start, tool_result). Note: there is no `agent_start` event emitted here — that comes from the runner.
_Avoid_: Custom agent, React agent

**Conversation**:
A persisted chat thread scoped to a Canvas. Tracks multi-turn user↔assistant exchanges. Messages include role, agent name, node_id, and event_type. In the Agent Chat UI, users can select which canvas they want to use when starting a new conversation, and the selection becomes locked once the conversation begins.
_Avoid_: Thread, chat session

Automatic naming: When the first user message is sent in a newly-created conversation (default name `New Conversation`), the backend attempts to generate a concise human-friendly title using a DSPy LLM call. If successful the conversation `name` is updated and a `conversation_renamed` WebSocket event is emitted so the frontend updates the Recent Chats list and current header immediately. If the LLM does not produce a suitable title, the backend falls back to a short excerpt from the user's question.

**Turn**:
A single user message + the resulting assistant messages (steps + final answer) within a Conversation.
_Avoid_: Exchange, round

**Workflow**:
A Canvas at the moment of execution — the resolved combination of Agent Nodes, Tool Nodes, and Edges that the backend compiles into live DSPy agent instances.
_Avoid_: Pipeline, graph, run

**Self-contained Distribution**:
A packaged application runtime that includes all required Agent Builder services locally and runs without Docker Compose.
_Avoid_: Docker stack, compose app, container bundle

**Execution Event**:
A JSON message streamed over WebSocket during a Workflow run. Types: run_start, agent_start, thought, tool_start, tool_result, handoff, final_answer, run_complete, error.
_Avoid_: Console, output, log, terminal

**Memory**:
Per-agent long-term storage backed by mem0 + Qdrant vector store. Each agent optionally gets three memory tools: `memory_search`, `memory_store`, `memory_get_all`.

Memory uses a single shared in-process `mem0.Memory` instance to avoid local Qdrant folder locking. The local Qdrant store is not safe for concurrent access by separate backend processes or reload workers.
_Avoid_: Long-term memory, storage

**RAG Documents**:
Text documents uploaded by a user and attached to a specific agent node (usually a Worker) to provide domain-specific context. At execution time, relevant chunks from these documents are retrieved and templated.
_Avoid_: Knowledge base, document store, uploaded files

**Canvas ZIP package**:
A ZIP archive export/import format for a Canvas. It contains a `manifest.json` plus agent-specific document files under `documents/{agent_id}/{doc_id}.txt`, allowing RAG documents to be preserved when moving teams between environments.
_Avoid_: bundle, tarball, archive format

**Conversation ZIP package**:
A ZIP archive export/import format for a Conversation. It contains a `manifest.json` with the conversation's messages, metadata, and plot references, as well as binary plot image files under `plots/`. During import, plot image IDs are remapped to prevent UUID collisions, and references in message content are updated automatically.
_Avoid_: thread export, conversation archive, text dump

**RAG Chunk Size**:
The maximum length (in characters) used when splitting RAG documents into paragraph-aligned chunks for embedding and retrieval.
_Avoid_: Split size, block length, character limit

**Observability**:
A dedicated MLflow UI page route (`/observability/:canvas_id`) that embeds the MLflow dashboard for tracing DSPy agent calls, tool invocations, and LLM interactions via `mlflow.dspy.autolog()`.
_Avoid_: Tracing, monitoring, dashboard

**Sandbox**:
An isolated Docker container session (managed via the `llm-sandbox` library) that executes all tool code in a sandboxed Python environment. Restricts access to host filesystem, host network, and host environment variables. Managed by the `canvas_server.sandbox.SandboxManager` singleton. Sandbox containers are assigned unique names of the format `sandbox-{uuid}` to enable target-specific clean-up via `make clean-sandbox` using the `--filter "name=^sandbox-"` Docker filter, avoiding accidental termination of other Python-based Docker containers.
_Avoid_: Deno subprocess, WASM runtime, Pyodide sandbox

**Tool Inspection**:
Extracting function metadata (name, parameter names, type hints, default values) from user-written Python code. Used by the Test Tool UI to generate argument input fields. Provided by `POST /api/tools/inspect`.
_Avoid_: Reflection, introspection, parsing

**Tool Test**:
Running a tool function in the sandbox with user-provided argument values and returning the result (output or error) to the UI. Provided by `POST /api/tools/test`.
_Avoid_: Playground, REPL, runner

**Plotting / PlotProvider**:
A capability that enables agents to generate visual charts and plots by executing python code containing matplotlib or plotly commands inside the sandboxed Docker session. The generated plots are captured, saved to the database as `ConversationPlot` records, and returned to the conversation as markdown image links referencing the database record (e.g., `![Plot](/api/plots/{plot_id})`). The execution engine also implements automatic plot link recovery (`ensure_plots_in_result`) to ensure that any generated plot is appended to the agent's final text response even if the LLM forgot to include it.
_Avoid_: Client-side charting, host-side plotting, inline plot generation

**Entry Point**:
A configuration flag (`is_entry_point`) on an Agent Node. When set to `True`, it designates that agent as the default starting node for workflow execution when no specific target agent ID is specified.
_Avoid_: Start node, root agent, entry node

**Human-in-the-Loop (HITL)**:
A runtime capability allowing worker agents and tools to pause execution and request human intervention. In worker agents, it triggers an input request for text input. In tools, it triggers an approval/denial request before execution.
_Avoid_: User-in-the-loop, human control

**ask_human**:
A built-in tool registered on worker agents that have Human-in-the-Loop enabled. When called by the agent, it suspends execution and requests textual input from the user via the chat UI.
_Avoid_: prompt_user, human_input

**Tool Approval**:
A capability where custom tool execution is paused until approved or denied by the user in the UI. If approved, the tool runs. If denied, the tool is skipped and a denial message is returned to the agent as the observation.
_Avoid_: function approval, script verification