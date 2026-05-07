# Canvas App — Architecture Plan

A visual canvas for composing AI agent workflows. Drag and wire agent nodes
and Python tool nodes, then execute them at runtime via the BeeAI Framework.

---

## Table of Contents

1. [Overview](#overview)
2. [Core Concepts](#core-concepts)
3. [System Diagram](#system-diagram)
4. [Technology Stack](#technology-stack)
5. [Project Structure](#project-structure)
6. [Database Schema](#database-schema)
7. [Backend Design](#backend-design)
8. [Frontend Design](#frontend-design)
9. [Execution Engine](#execution-engine)
10. [WebSocket Wire Protocol](#websocket-wire-protocol)
11. [Edge Validation Rules](#edge-validation-rules)
12. [Execution States (Frontend)](#execution-states-frontend)
13. [Docker & Deployment](#docker--deployment)
14. [API Endpoints](#api-endpoints)

---

## Overview

Users visually wire AI agents and custom Python tools on a canvas. Behind the
scenes a FastAPI backend uses the [BeeAI Framework](https://github.com/i-am-bee/beeai-framework)
to dynamically compile the graph into live `RequirementAgent` instances,
wire them together with `HandoffTool`, and execute the workflow — streaming
every thought, tool call, and result back to the UI in real time.

---

## Core Concepts

| Concept              | Description                                                                                   |
|----------------------|-----------------------------------------------------------------------------------------------|
| **Agent Node**       | A visual block representing a `RequirementAgent`. Has name, role, instructions, LLM model.    |
| **Tool Node**        | A visual block containing user-written Python code. Compiled into a beeai `Tool` at runtime.  |
| **Edge**             | A visual connection. Agent→Tool = that agent can call that tool. Agent→Agent = a handoff.     |
| **Implicit Orchestrator** | A hidden top-level agent created at run time. Routes the user prompt to agents via handoff. |

---

## System Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│  REACT FRONTEND (localhost:5173)                                   │
│                                                                    │
│  ┌─ CanvasView (ReactFlow) ─────┐  ┌─ Sidebar ─────────────────┐ │
│  │                               │  │  AgentEditor              │ │
│  │  [Agent A]──→[Tool 1]        │  │  ToolEditor (Monaco)      │ │
│  │     │                         │  │  ExecutionLog (streaming)  │ │
│  │     ▼ (handoff)               │  └──────────────────────────┘ │
│  │  [Agent B]──→[Tool 2]        │                                 │
│  │                               │                                 │
│  └───────────────────────────────┘                                 │
│                                                                    │
│  HTTP REST + WebSocket ◄─────────────────────────────────────────►│
└──────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│  FASTAPI BACKEND (localhost:8000)                                 │
│                                                                    │
│  Canvas Repo ──→ Canvas Runner ──→ BeeAI Framework                │
│  (PostgreSQL)     parse graph        RequirementAgent              │
│                   build tools        HandoffTool                   │
│                   wire agents        CustomTool (@tool decorator)  │
│                   stream events      ChatModel (multi-provider)    │
│                                      EventEmitter → WebSocket      │
└──────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│  POSTGRESQL (pgvector/pg17)                                       │
│  canvases, agent_nodes, tool_nodes, edges                         │
└──────────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

| Layer              | Technology                                               |
|--------------------|----------------------------------------------------------|
| Frontend           | React 19 + TypeScript + Vite 6                           |
| Canvas             | @xyflow/react (ReactFlow v12)                            |
| Code Editing       | @monaco-editor/react                                     |
| State Management   | zustand                                                  |
| Styling            | Tailwind CSS 4 + shadcn/ui                               |
| Icons              | lucide-react                                             |
| Backend            | Python 3.12+ / FastAPI / async                           |
| Agent Framework    | beeai-framework (Python)                                 |
| LLM Default        | Ollama (configurable: OpenAI, Anthropic, Groq, etc.)     |
| Database           | PostgreSQL 17 + pgvector (async SQLAlchemy 2.0 + Alembic)|
| Streaming          | WebSocket for real-time agent event streaming            |
| Container Runtime  | Docker + Docker Compose                                  |

---

## Project Structure

```
canvas-app/
├── docker-compose.yml
├── ARCHITECTURE.md
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   └── src/canvas_server/
│       ├── __init__.py
│       ├── main.py             # FastAPI app, CORS, lifespan (startup/shutdown)
│       ├── config.py           # Settings via pydantic-settings (DB URL, LLM defaults)
│       ├── database.py         # Async engine, session factory
│       ├── models/
│       │   ├── __init__.py
│       │   ├── canvas.py       # SQLAlchemy ORM: Canvas, AgentNode, ToolNode, Edge
│       │   └── api.py          # Pydantic request/response schemas (API models)
│       ├── repos/
│       │   ├── __init__.py
│       │   └── canvas_repo.py  # Async CRUD operations on canvas data
│       ├── runner.py           # Core execution engine: graph → live agents → stream events
│       ├── tool_factory.py     # Python code string → beeai Tool (@tool decorator + exec)
│       ├── routes/
│       │   ├── __init__.py
│       │   ├── canvas.py       # REST CRUD endpoints (/api/canvas)
│       │   └── execute.py      # WebSocket execution endpoint (/ws/canvas/{id}/run)
│       └── exceptions.py       # Custom error types and exception handlers
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── package-lock.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tsconfig.app.json
│   ├── tsconfig.node.json
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── components/
│       │   ├── layout/
│       │   │   └── AppShell.tsx          # Sidebar + toolbar + canvas layout
│       │   ├── canvas/
│       │   │   ├── CanvasView.tsx         # ReactFlow container (zoom, pan, minimap)
│       │   │   ├── AgentNode.tsx          # Custom node — name, model badge, status
│       │   │   ├── ToolNode.tsx           # Custom node — name, code snippet preview
│       │   │   └── CustomEdge.tsx         # Dashed for handoff, solid for tool access
│       │   ├── sidebar/
│       │   │   ├── Sidebar.tsx            # Tabs: Properties | Run
│       │   │   ├── AgentEditor.tsx        # Name, role, instructions, model select
│       │   │   ├── ToolEditor.tsx         # Monaco Python editor, tool name
│       │   │   └── ExecutionLog.tsx       # Real-time streaming event list
│       │   └── toolbar/
│       │       └── CanvasToolbar.tsx      # Add Agent, Add Tool, Run, Clear
│       ├── store/
│       │   └── canvasStore.ts             # zustand: nodes, edges, execution state
│       ├── hooks/
│       │   ├── useCanvasExecution.ts      # WebSocket connect, dispatch events
│       │   └── useCanvasPersistence.ts    # Auto-save debounce to backend
│       ├── types/
│       │   └── index.ts                   # Shared TypeScript types
│       ├── lib/
│       │   └── api.ts                     # fetch wrappers for REST endpoints
│       └── styles/
│           └── globals.css
```

---

## Database Schema (PostgreSQL)

```sql
CREATE TABLE canvases (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name       TEXT NOT NULL DEFAULT 'Untitled Canvas',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE agent_nodes (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canvas_id    UUID NOT NULL REFERENCES canvases(id) ON DELETE CASCADE,
    name         TEXT NOT NULL DEFAULT 'Agent',
    role         TEXT NOT NULL DEFAULT '',
    instructions TEXT NOT NULL DEFAULT '',
    model_name   TEXT NOT NULL DEFAULT 'ollama:llama3.1',
    position_x   DOUBLE PRECISION NOT NULL DEFAULT 0,
    position_y   DOUBLE PRECISION NOT NULL DEFAULT 0
);

CREATE INDEX idx_agent_nodes_canvas ON agent_nodes(canvas_id);

CREATE TABLE tool_nodes (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canvas_id  UUID NOT NULL REFERENCES canvases(id) ON DELETE CASCADE,
    name       TEXT NOT NULL DEFAULT 'Tool',
    code       TEXT NOT NULL DEFAULT '',
    position_x DOUBLE PRECISION NOT NULL DEFAULT 0,
    position_y DOUBLE PRECISION NOT NULL DEFAULT 0
);

CREATE INDEX idx_tool_nodes_canvas ON tool_nodes(canvas_id);

CREATE TYPE edge_type_enum AS ENUM ('tool_access', 'handoff');

CREATE TABLE edges (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canvas_id       UUID NOT NULL REFERENCES canvases(id) ON DELETE CASCADE,
    source_node_id  UUID NOT NULL,
    target_node_id  UUID NOT NULL,
    edge_type       edge_type_enum NOT NULL
);

CREATE INDEX idx_edges_canvas ON edges(canvas_id);
```

---

## Backend Design

### config.py

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://canvas:canvas@localhost:5432/canvas_db"
    default_llm: str = "ollama:llama3.1"
    cors_origins: list[str] = ["http://localhost:5173"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
```

### models/canvas.py — SQLAlchemy ORM

```python
from sqlalchemy.orm import Mapped, mapped_column, relationship
from canvas_server.database import Base

class Canvas(Base):
    __tablename__ = "canvases"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(default="Untitled Canvas")
    agent_nodes = relationship("AgentNode", back_populates="canvas",
                                cascade="all, delete-orphan")
    tool_nodes  = relationship("ToolNode", back_populates="canvas",
                                cascade="all, delete-orphan")
    edges       = relationship("Edge", back_populates="canvas",
                                cascade="all, delete-orphan")

class AgentNode(Base):
    __tablename__ = "agent_nodes"
    id         = ...  # UUID PK
    canvas_id  = ...  # FK → canvases
    name: str  = mapped_column(default="Agent")
    role: str  = mapped_column(default="")
    instructions: str = mapped_column(default="")
    model_name: str   = mapped_column(default="ollama:llama3.1")
    position_x: float = mapped_column(default=0)
    position_y: float = mapped_column(default=0)

class ToolNode(Base):
    __tablename__ = "tool_nodes"
    id         = ...  # UUID PK
    canvas_id  = ...  # FK → canvases
    name: str  = mapped_column(default="Tool")
    code: str  = mapped_column(default="")
    position_x: float = mapped_column(default=0)
    position_y: float = mapped_column(default=0)

class Edge(Base):
    __tablename__ = "edges"
    id              = ...  # UUID PK
    canvas_id       = ...  # FK → canvases
    source_node_id  = ...  # UUID
    target_node_id  = ...  # UUID
    edge_type       = ...  # enum: tool_access | handoff
```

### repos/canvas_repo.py — Async CRUD

```python
class CanvasRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, name: str = "Untitled Canvas") -> Canvas: ...
    async def get(self, canvas_id: UUID) -> Canvas | None: ...
    async def delete(self, canvas_id: UUID) -> bool: ...
    async def save_nodes_and_edges(
        self, canvas_id: UUID,
        agents: list[AgentNodeInput],
        tools: list[ToolNodeInput],
        edges: list[EdgeInput],
    ) -> Canvas: ...
```

---

## Frontend Design

### Component Breakdown

**CanvasView.tsx** — ReactFlow wrapper

- Renders `AgentNode` and `ToolNode` custom nodes.
- Supports adding nodes via context menu (right-click empty area) or toolbar.
- Drag to connect — validates edge types (see [Edge Validation Rules](#edge-validation-rules)).
- On node/edge change → update zustand store.

**AgentNode.tsx** — Custom ReactFlow node

- Displays agent name, model badge (e.g. `llama3.1`), role snippet.
- Animated border/glow when agent is "active" during execution.
- Click to select → Properties panel shows AgentEditor.

**ToolNode.tsx** — Custom ReactFlow node

- Displays tool name + first 3 lines of code as preview.
- Same active state animation during execution.
- Click to select → Properties panel shows ToolEditor.

**AgentEditor.tsx** — Config panel (right sidebar, "Properties" tab)

- Fields: name, role, instructions (textarea), model select dropdown.
- Model options: common Ollama models + manual input for custom/cloud providers.

**ToolEditor.tsx** — Monaco-based Python editor (right sidebar, "Properties" tab)

- Fields: tool name, code editor (Monaco with Python syntax highlighting).
- Auto-parse button: extracts function signature and shows derived input schema.

**ExecutionLog.tsx** — Streaming event viewer (right sidebar, "Run" tab)

- Accordion-style grouped by agent.
- Each event type has distinct styling:
  - `thought` → italic, muted color
  - `tool_call` → monospace, code-style background
  - `tool_result` → monospace, darker background
  - `handoff` → dashed border, arrow icon
  - `final_answer` → bold, accent color
- Auto-scrolls to latest event during execution.

**CanvasToolbar.tsx** — Top toolbar

- Add Agent button → drops a new AgentNode in the center of the viewport.
- Add Tool button → drops a new ToolNode.
- Run button → disabled during execution, shows spinner while running.
- Clear button → removes all nodes and edges.
- Canvas name field (editable).

### State Management (zustand)

```typescript
// store/canvasStore.ts

type ExecutionStatus = "idle" | "running" | "done" | "error";

interface CanvasStore {
  canvasId: string | null;
  canvasName: string;
  nodes: Node[];
  edges: Edge[];
  selectedNodeId: string | null;
  executionStatus: ExecutionStatus;
  executionEvents: ExecutionEvent[];

  // Actions
  setCanvas: (id: string, name: string) => void;
  setNodes: (nodes: Node[]) => void;
  setEdges: (edges: Edge[]) => void;
  selectNode: (id: string | null) => void;
  addExecutionEvent: (event: ExecutionEvent) => void;
  setExecutionStatus: (status: ExecutionStatus) => void;
  clearExecution: () => void;
}
```

### types/index.ts — Shared Types

```typescript
interface AgentNodeData {
  id: string;
  name: string;
  role: string;
  instructions: string;
  modelName: string;
}

interface ToolNodeData {
  id: string;
  name: string;
  code: string;
}

type ExecutionEvent =
  | { type: "run_start"; canvas_id: string }
  | { type: "agent_start"; agent: string }
  | { type: "thought"; agent: string; content: string }
  | { type: "tool_call"; agent: string; tool: string; input: Record<string, unknown> }
  | { type: "tool_result"; agent: string; tool: string; output: string }
  | { type: "handoff"; from: string; to: string }
  | { type: "final_answer"; content: string }
  | { type: "run_complete"; result: string }
  | { type: "error"; message: string; agent?: string };
```

### hooks/useCanvasExecution.ts — WebSocket Consumer

```typescript
const useCanvasExecution = () => {
  const wsRef = useRef<WebSocket | null>(null);
  const addEvent = useCanvasStore((s) => s.addExecutionEvent);
  const setStatus = useCanvasStore((s) => s.setExecutionStatus);

  const run = (canvasId: string, prompt: string) => {
    setStatus("running");
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(
      `${protocol}//${import.meta.env.VITE_API_HOST || "localhost:8000"}/ws/canvas/${canvasId}/run`
    );

    ws.onopen = () => ws.send(JSON.stringify({ prompt }));
    ws.onmessage = (evt) => {
      const event = JSON.parse(evt.data) as ExecutionEvent;
      addEvent(event);
      if (event.type === "run_complete") setStatus("done");
      if (event.type === "error") setStatus("error");
    };
    ws.onerror = () => setStatus("error");
    ws.onclose = () => {
      if (wsRef.current === ws) wsRef.current = null;
    };
    wsRef.current = ws;
  };

  const abort = () => { wsRef.current?.close(); setStatus("idle"); };

  return { run, abort };
};
```

### hooks/useCanvasPersistence.ts — Auto-save

```typescript
// Debounces (500ms) and PUTs full canvas state to /api/canvas/{id}
// Triggered whenever nodes or edges change in zustand.
```

---

## Execution Engine

### runner.py — The Core

```
Input:  canvas_id (UUID) + user_prompt (str)
Output: WebSocket event stream (asyncio + beeai EventEmitter)

Step 1 — Load graph
  - Fetch Canvas with all agent_nodes, tool_nodes, edges from DB.

Step 2 — Build graph
  - For each ToolNode → compile code into a beeai Tool (tool_factory.py)
  - For each AgentNode:
    - Collect tools from outgoing tool_access edges → tools list
    - Collect handoff edges to other agents → HandoffTool list
    - Create RequirementAgent with its tools + handoff tools

Step 3 — Create implicit orchestrator
  - One RequirementAgent that has a HandoffTool pointing to every
    canvas-level agent.
  - Has ThinkTool to plan routing.
  - Receives the user prompt and decides which agent(s) to hand off to.

Step 4 — Wire events to WebSocket
  - Register listeners on every agent's EventEmitter for:
    - "thought", "tool_call", "tool_result", "handoff", "final_answer"
  - Each event → serialize to JSON → send over WebSocket.

Step 5 — Execute
  - await orchestrator.run(user_prompt)
  - On completion → send {"type": "run_complete", ...}
  - On FrameworkError → send {"type": "error", ...}

Cleanup
  - Cancel running agent tasks on WebSocket disconnect.
```

### tool_factory.py — Python Code to BeeAI Tool

```python
"""
Transforms a raw Python code string into a beeai Tool at runtime.

Expected input (user's code):
    def search_database(query: str) -> str:
        \"\"\"Search the internal database for the given query.\"\"\"
        import sqlite3
        # ... implementation ...
        return results

The factory:
1. Extracts the top-level function name, docstring, and signature.
2. Wraps it with beeai's @tool decorator.
3. Returns a callable Tool ready for use by any RequirementAgent.
"""

import inspect
import textwrap
from beeai_framework.tools import tool, StringToolOutput

async def compile_tool_from_code(name: str, code: str) -> Tool:
    # 1. exec the code in an isolated namespace
    namespace: dict = {}
    exec(code, namespace)

    # 2. Find the first callable that isn't a builtin
    user_func = None
    for val in namespace.values():
        if callable(val) and not inspect.isbuiltin(val) and val.__module__ != "builtins":
            user_func = val
            break

    if not user_func:
        raise ToolCompilationError("No callable function found in tool code.")

    # 3. Wrap with beeai @tool
    @tool
    def dynamic_tool(**kwargs) -> StringToolOutput:
        result = user_func(**kwargs)
        return StringToolOutput(str(result))

    # Assign metadata from original function
    dynamic_tool.__name__ = name
    dynamic_tool.__doc__ = user_func.__doc__ or ""

    return dynamic_tool
```

---

## WebSocket Wire Protocol

All messages are JSON, one message per line. Events are sent in chronological
order as they happen during agent execution.

```jsonc
// Run lifecycle
{"type": "run_start",    "canvas_id": "550e8400-e29b-41d4-a716-446655440000"}

// Agent activation
{"type": "agent_start",  "agent": "Researcher"}

// Reasoning
{"type": "thought",      "agent": "Researcher",
                         "content": "I need to query the database to find the user's records."}

// Tool usage
{"type": "tool_call",    "agent": "Researcher", "tool": "DatabaseLookup",
                         "input": {"query": "SELECT * FROM users WHERE id=42"}}

{"type": "tool_result",  "agent": "Researcher", "tool": "DatabaseLookup",
                         "output": "[{\"id\": 42, \"name\": \"Alice\"}]"}

// Handoff between agents
{"type": "handoff",      "from": "Orchestrator", "to": "WeatherAgent"}

// Final answer
{"type": "final_answer", "content": "The weather in Rome next weekend will be sunny, 22\u00b0C."}

// Completion
{"type": "run_complete", "result": "The weather in Rome..."}

// Error
{"type": "error",        "message": "Tool 'DatabaseLookup' timed out after 30s.",
                         "agent": "Researcher"}
```

---

## Edge Validation Rules

| Source Node | Target Node | Allowed? | Edge Type              | Visual Style       |
|-------------|-------------|----------|------------------------|--------------------|
| Agent       | Tool        | Yes      | `tool_access`           | Solid line          |
| Agent       | Agent       | Yes      | `handoff`               | Dashed line + arrow |
| Tool        | Tool        | No       | —                      | —                  |
| Tool        | Agent       | No       | —                      | —                  |

Enforced both on the frontend (ReactFlow `isValidConnection`) and on the
backend before execution (schema validation).

---

## Execution States (Frontend)

| State     | Canvas Behavior                                                                               |
|-----------|-----------------------------------------------------------------------------------------------|
| `idle`    | Normal editing mode. Run button enabled. Nodes can be moved, added, connected, deleted.       |
| `running` | Run button shows spinner. Nodes highlight as active during their turn. ExecutionLog streams.  |
|           | All canvas interactions (drag, add, delete, connect) are disabled.                            |
| `done`    | Final answer displayed prominently in ExecutionLog. All editing restored.                     |
| `error`   | Error message shown in ExecutionLog with red styling. All editing restored.                   |

---

## Docker & Deployment

### docker-compose.yml

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg17
    environment:
      POSTGRES_USER: canvas
      POSTGRES_PASSWORD: canvas
      POSTGRES_DB: canvas_db
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U canvas -d canvas_db"]
      interval: 5s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: ./backend
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql+asyncpg://canvas:canvas@postgres:5432/canvas_db
      DEFAULT_LLM: ollama:llama3.1
      OLLAMA_HOST: http://ollama:11434
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - ./backend/src:/app/src

  frontend:
    build:
      context: ./frontend
    ports:
      - "5173:5173"
    environment:
      VITE_API_HOST: localhost:8000
    depends_on:
      - backend
    volumes:
      - ./frontend:/app
      - /app/node_modules

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    profiles:
      - ollama

volumes:
  pgdata:
  ollama_data:
```

### backend/Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY alembic/ alembic/
COPY src/ src/

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn canvas_server.main:app --host 0.0.0.0 --port 8000 --reload"]
```

### frontend/Dockerfile

```dockerfile
FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

### backend/requirements.txt

```
fastapi>=0.115.0
uvicorn[standard]>=0.34.0
beeai-framework>=0.1.0
sqlalchemy[asyncio]>=2.0.36
asyncpg>=0.30.0
alembic>=1.14.0
pydantic>=2.10
pydantic-settings>=2.7
python-multipart>=0.0.18
websockets>=14.1
```

### frontend/package.json (key dependencies)

```json
{
  "dependencies": {
    "react": "^19.0",
    "react-dom": "^19.0",
    "@xyflow/react": "^12.5",
    "@monaco-editor/react": "^4.7",
    "zustand": "^5.0",
    "lucide-react": "^0.470"
  },
  "devDependencies": {
    "typescript": "^5.7",
    "vite": "^6.1",
    "@vitejs/plugin-react": "^4.3",
    "tailwindcss": "^4.0",
    "postcss": "^8.5",
    "autoprefixer": "^10.4"
  }
}
```

### Usage Commands

```bash
# Full stack with local Ollama (requires models to be pulled):
docker compose --profile ollama up

# Full stack using only cloud LLMs (no local Ollama):
docker compose up

# Run only database and backend (for API-only testing):
docker compose up postgres backend

# Pull a model into the running Ollama container:
docker compose --profile ollama exec ollama ollama pull llama3.1

# Run database migrations manually:
docker compose exec backend alembic upgrade head

# Tear down all containers and volumes:
docker compose --profile ollama down -v
```

---

## API Endpoints

### Canvas CRUD

| Method   | Path                   | Description                                     |
|----------|------------------------|-------------------------------------------------|
| `POST`   | `/api/canvases`        | Create a new canvas (returns canvas with ID).   |
| `GET`    | `/api/canvases`        | List all canvases (id + name).                  |
| `GET`    | `/api/canvases/{id}`   | Get full canvas with all nodes and edges.       |
| `PUT`    | `/api/canvases/{id}`   | Upsert nodes and edges for the canvas.          |
| `DELETE` | `/api/canvases/{id}`   | Delete canvas and all associated data.          |

### Execution

| Method | Path                              | Description                                   |
|--------|-----------------------------------|-----------------------------------------------|
| `WS`   | `/ws/canvases/{id}/run`          | Open WebSocket. Client sends `{"prompt":"..."}` |
|        |                                   | after connect. Server streams execution events. |

### PUT `/api/canvases/{id}` — Request Body

```jsonc
{
  "name": "My Workflow",
  "nodes": {
    "agents": [
      {
        "id": "a1-uuid",
        "name": "Researcher",
        "role": "You are a research assistant.",
        "instructions": "Look up facts and provide citations.",
        "model_name": "ollama:llama3.1",
        "position_x": 100,
        "position_y": 200
      }
    ],
    "tools": [
      {
        "id": "t1-uuid",
        "name": "DatabaseLookup",
        "code": "def search(query: str) -> str:\n    ...",
        "position_x": 400,
        "position_y": 200
      }
    ]
  },
  "edges": [
    {
      "id": "e1-uuid",
      "source_node_id": "a1-uuid",
      "target_node_id": "t1-uuid",
      "edge_type": "tool_access"
    }
  ]
}
```

### GET `/api/canvases/{id}` — Response Body

Same shape as the PUT request body, with database-level `created_at` and
`updated_at` added at the root level.

