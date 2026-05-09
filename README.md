# MJ Agentic Framework

![Canvas](./canvas_screen.png)

Visual canvas for composing and executing AI agent workflows. Drag agent and tool nodes, wire them with edges, and run multi-agent teams backed by the [BeeAI Framework](https://github.com/i-am-bee/beeai-framework).

## Quick Start

```bash
docker compose up
```

Launches PostgreSQL, backend (port 8000), frontend (port 5173), and Ollama. Open `http://localhost:5173`.

Run migrations on first launch:
```bash
docker compose exec backend uv run alembic upgrade head
```

## Architecture

- **Frontend:** React 19 + TypeScript + Vite, ReactFlow canvas, Tailwind CSS, zustand state
- **Backend:** Python 3.12+ / FastAPI, BeeAI Framework for agent execution, WebSocket streaming
- **Database:** PostgreSQL 17 (asyncpg) in production, SQLite (aiosqlite) for tests
- **LLM:** Ollama (configurable model per agent type via `.env`)

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

- **Router agents** orchestrate — they delegate tasks to worker sub-agents via transfer actions
- **Worker agents** perform specialized work with optional Python tools
- Execution starts from the first agent node, or a specific agent (`target_agent_id`)
- All events stream over WebSocket with `node_id` for real-time canvas highlighting
- Sub-agent outputs appear as tool results; the final answer comes from the master agent
- Thoughts are collapsed by default (click to expand)

## Configuration

`backend/.env`:
| Variable | Default | Description |
|---|---|---|
| `LLM_BASE_URL` | `http://192.168.1.120:11434` | Ollama server |
| `LLM_MODEL_ROUTER` | `ollama:kimi-k2.6:cloud` | Model for router agents |
| `LLM_MODEL_AGENT` | `ollama:kimi-k2.6:cloud` | Model for worker agents |

## Running Locally (without Docker)

**Backend:**
```bash
cd backend
uv sync && uv sync --group test
uv run alembic upgrade head
uv run uvicorn canvas_server.main:app --host 0.0.0.0 --port 8000 --reload
```

**Frontend:**
```bash
cd frontend
npm install && npm run dev
```

## Development

### Backend

| Command | Purpose |
|---|---|
| `uv run pytest tests/ -v` | Run tests (SQLite, no real LLM calls) |
| `uv run ruff check .` | Lint |
| `uv run ruff check . --fix` | Auto-fix lint issues |
| `uv run alembic revision --autogenerate -m "...""` | Create DB migration |

### Frontend

| Command | Purpose |
|---|---|
| `npm run dev` | Dev server |
| `npm run build` | Production build (`tsc` + `vite build`) |
| `npx tsc --noEmit` | Type-check only |

### CI

GitHub Actions on push/PR to `main`: installs uv with Python 3.14, runs `ruff` and `pytest`.

## API Endpoints

### Canvases
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/canvases` | Create canvas |
| `GET` | `/api/canvases` | List all canvases |
| `GET` | `/api/canvases/{id}` | Get full graph (nodes + edges) |
| `PUT` | `/api/canvases/{id}` | Save nodes and edges |
| `DELETE` | `/api/canvases/{id}` | Delete canvas |
| `POST` | `/api/canvases/import` | Import from JSON |
| `GET` | `/api/canvases/{id}/export` | Export as JSON |

### Conversations
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/canvases/{id}/conversations` | Create conversation |
| `GET` | `/api/canvases/{id}/conversations` | List conversations |
| `GET` | `/api/canvases/{id}/conversations/{cid}` | Get conversation with messages |
| `DELETE` | `/api/canvases/{id}/conversations/{cid}` | Delete conversation |

### Execution
| Method | Path | Description |
|---|---|---|
| `WS` | `/ws/conversations/{cid}/run` | Run workflow, stream events |

WebSocket sends `{"prompt": "...", "target_agent_id?": "uuid"}` and receives streaming `ExecutionEvent` JSON (types: `run_start`, `agent_start`, `thought`, `handoff`, `tool_result`, `final_answer`, `run_complete`, `error`).
