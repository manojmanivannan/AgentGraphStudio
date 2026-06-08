# Agent Builder — Visual AI Workflow Canvas

![Canvas](./canvas_screen.png)

Visual canvas for composing and executing AI agent workflows. Drag agent and tool
nodes, wire them with edges, and run multi-agent teams powered by
[DSPy](https://dspy.ai/).

---

## Documentation

| Document | Description |
|---|---|
| **[CLAUDE.md](./CLAUDE.md)** | Developer context — where things live, data flow, change recipes, TDD requirements |
| **[docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md)** | Full architecture — tech stack, database schema, execution engine, frontend, testing |
| **[CONTEXT.md](./CONTEXT.md)** | Canonical glossary of domain terms |

---

## Quick Start

```bash
docker compose up
```

Launches PostgreSQL (pgvector), backend (port 8000), frontend (port 5173), and
MLflow (port 5000). Open `http://localhost:5173`.

> **Requires an LLM backend.** Defaults to Ollama on the host machine (`http://192.168.1.120:11434`).
> Configure via `backend/.env`. See [Configuration](#configuration) below.

---

## What This Is

This is an **agent builder** — a visual IDE for creating multi-agent AI workflows:

1. **Drag agents** onto a canvas — each with a role, instructions, and model.
2. **Wire tools** — write Python functions agents can call; test them instantly in the UI.
3. **Connect agents** — handoffs let one agent delegate to another.
4. **Attach RAG Documents** — upload domain-specific text documents to Worker agents, configure paragraph-aligned chunking, and dynamically query/inject search results using the `{{ rag_document }}` template placeholder at execution time.
5. **Export/Import ZIP packages** — export a canvas as a ZIP archive containing a manifest and per-agent RAG documents, or import it back to preserve team structure and document artifacts.
6. **Run** — watch agents reason, call tools, use memory, run RAG queries, and collaborate in real-time.

**Two agent types:**
- **Workers** — execute tasks by reasoning and calling tools (DSPy ReAct loop). Can have RAG documents.
- **Routers** — orchestrate by handing off tasks to other agents.

---

## Quick Start (Without Docker)

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install uv && uv sync
uv run alembic upgrade head
uv run uvicorn canvas_server.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Database

Requires PostgreSQL 17 with pgvector running on localhost:5432:
```
createdb canvas_db
```

Or use SQLite for development (set `DATABASE_URL=sqlite+aiosqlite:///dev.db`).

---

## Architecture Overview

- **Frontend:** React 19 + TypeScript + Vite, ReactFlow canvas, Tailwind CSS, zustand
- **Backend:** Python 3.12+ / FastAPI, **DSPy** for agent execution, WebSocket streaming
- **Tool Sandbox:** Deno + Pyodide (WASM Python via DSPy PythonInterpreter)
- **Database:** PostgreSQL 17 + pgvector (asyncpg), SQLite for tests
- **LLM:** Configurable per agent — defaults to Ollama
- **Memory:** mem0 + local Qdrant vector store, per-agent via `user_id` scoping and a shared in-process mem0 singleton
- **Observability:** MLflow DSPy autolog

### Layout & Routes

The application features a clean, multi-page router architecture:

- **Landing Page** (`/`): Dashboard listing all saved agent canvases with search and import options.
- **Canvas Editor Page** (`/canvas/:canvas_id`): Interactive visual graph workspace with:
  - **TopBar**: Canvas name, save status, and quick links to open **Observability** or **Agent Chat**.
  - **SidebarRail**: Actions to add agent/tool nodes, clear the graph, export/import, and toggle the theme.
  - **CanvasView**: ReactFlow workspace for layout and wiring of agents/tools.
  - **PropertiesOverlay**: Drawer panel for modifying selected agent parameters, memory settings, or Monaco Python tool code.
- **Agent Chat Page** (`/chat/:conversation_id`): Dedicated dual-pane conversation workspace featuring past conversations list, thread deletions, real-time thought/tool/handoff streaming view, and final answer history.
- **Observability Page** (`/observability/:canvas_id`): Dedicated workspace housing the full-screen MLflow iframe alongside quick-jump navigation controls back to the chat page or canvas editor.

---

## Configuration

`backend/.env`:

| Variable | Default | Description |
|---|---|---|
| `LLM_BASE_URL` | `http://192.168.1.120:11434` | LLM server URL |
| `LLM_MODEL` | `ollama_chat/gemma4:31b` | Default model for agents |
| `MLFLOW_TRACKING_URI` | `http://mlflow:5000` | MLflow server URL |
| `MLFLOW_ENABLED` | `true` | Set `false` to skip MLflow init (CI) |
| `MEM0_LLM_MODEL` | `gemma4:31b` | Model used by mem0 |
| `MEM0_EMBEDDER_PROVIDER` | `ollama` | Embedding provider (e.g. `ollama`, `openai`) used by mem0 & RAG |
| `MEM0_EMBEDDER_MODEL` | `nomic-embed-text` | Embedding model name used by mem0 & RAG |
| `MEM0_EMBEDDER_DIMENSIONS` | `768` | Embedding dimensions used by mem0 & RAG |
| `DATABASE_URL` | `postgresql+asyncpg://...` | Override for SQLite testing |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | Allowed origins |

> Note: local Qdrant storage is not safe for concurrent access by multiple backend processes or reload/proxy workers. The backend shares a single in-process mem0 client to avoid repeated Qdrant folder conflicts.

---

## Development

### Backend Tests
```bash
cd backend
uv run pytest -v
# Run the canvas export/import ZIP coverage tests:
uv run python -m pytest tests/test_routes_canvas.py -q
```

### Frontend Tests
```bash
cd frontend
npx vitest run
npx vitest run --coverage    # Coverage report
npx tsc --noEmit             # Type checking
```

### E2E Tests
```bash
cd frontend
npm run test:e2e
```

### Migrations
```bash
cd backend
uv run alembic revision --autogenerate -m "description"
uv run alembic upgrade head
```

