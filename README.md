# Canvas — Visual AI Agent Workflow Builder

![Canvas](./canvas_screen.png)

Visual canvas for composing and executing AI agent workflows. Drag agent and tool nodes, wire them with edges, and run multi-agent teams powered by [DSPy](https://dspy.ai/).

## Quick Start

```bash
docker compose up
```

Launches PostgreSQL (pgvector), backend (port 8000), frontend (port 5173), and MLflow (port 5000). Open `http://localhost:5173`.

## Architecture

- **Frontend:** React 19 + TypeScript + Vite, ReactFlow canvas, Tailwind CSS, zustand state
- **Backend:** Python 3.12+ / FastAPI, DSPy for agent execution, WebSocket streaming
- **Database:** PostgreSQL 17 + pgvector (asyncpg)
- **LLM:** Configurable per agent — defaults to Ollama (`ollama_chat/gemma4:31b`)
- **Memory:** mem0 with Qdrant vector store, per-agent memory instances
- **Observability:** MLflow DSPy autolog for tracing

### Layout & UX

The workspace has four zones:

| Zone | Description |
|---|---|
| **CanvasToolbar** (top) | Add agents/tools, clear, import/export workflows |
| **CanvasView** (center) | Drag-and-drop agent/tool nodes, wire edges |
| **PropertiesSidebar** (collapsible, w-12/w-64) | Edit agent role, instructions, model, or tool code |
| **ChatPanel** (right, w-96) | Per-conversation chat, streaming, node highlighting |

Agent and tool nodes glow green when active during execution.

### Conversations

Each canvas has persistent conversations (chat threads). Full conversation history is injected as context for follow-up messages. Messages are stored with role, agent name, node ID, and event type.

### Agent Execution Model

- **Worker agents** are DSPy `ReAct` modules — they reason through tool calls iteratively
- **Router agents** orchestrate — they delegate tasks to worker sub-agents via handoff tools (plain async callables)
- Execution starts from the first agent node, or a specific agent (`target_agent_id`)
- All events stream over WebSocket with `node_id` for real-time canvas highlighting
- Sub-agent outputs appear as tool results; the final answer comes from the router agent
- Thoughts are collapsed by default (click to expand)

### Memory

Agents can optionally enable per-agent memory powered by mem0. When enabled, three memory tools are automatically attached:

| Tool | Description |
|---|---|
| `memory_search` | Search stored memories by query |
| `memory_store` | Store a new memory |
| `memory_get_all` | Retrieve all stored memories |

### Observability

MLflow DSPy autolog captures all agent calls, tool invocations, and LLM interactions. The built-in ObservabilityView embeds the MLflow UI directly in the canvas.

## Configuration

`backend/.env`:

| Variable | Default | Description |
|---|---|---|
| `LLM_BASE_URL` | `http://192.168.1.120:11434` | LLM server URL |
| `LLM_MODEL` | `ollama_chat/gemma4:31b` | Default model for agents |
| `MLFLOW_TRACKING_URI` | `http://mlflow:5000` | MLflow server URL |
| `MEM0_LLM_MODEL` | `gemma4:31b` | Model used by mem0 |
| `MEM0_EMBEDDER_MODEL` | `nomic-embed-text` | Embedding model for mem0 |

