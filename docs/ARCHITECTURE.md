# Agent Builder — Architecture

A visual canvas for composing AI agent workflows. Drag agent and tool nodes, wire
them with edges, and execute multi-agent teams powered by [DSPy](https://dspy.ai/).

> This document describes the **actual** codebase. The project originally used
> beeai-framework and was migrated to DSPy. All beeai references in old docs are
> obsolete — only DSPy remains.

---

## Table of Contents

1. [Technology Stack](#technology-stack)
2. [System Diagram](#system-diagram)
3. [Layout & UX Zones](#layout--ux-zones)
4. [Project Structure](#project-structure)
5. [Database Schema](#database-schema)
6. [API Endpoints](#api-endpoints)
7. [WebSocket Wire Protocol](#websocket-wire-protocol)
8. [Backend Architecture](#backend-architecture)
9. [Execution Engine](#execution-engine)
10. [Agent Execution Model](#agent-execution-model)
11. [Memory Architecture](#memory-architecture)
12. [Conversation Lifecycle](#conversation-lifecycle)
13. [Frontend Architecture](#frontend-architecture)
14. [CSS Design System & Theming](#css-design-system--theming)
15. [Docker & Deployment](#docker--deployment)
16. [Observability](#observability)

---

## Technology Stack

| Layer              | Technology                                                           |
|--------------------|----------------------------------------------------------------------|
| Frontend           | React 19 + TypeScript + Vite 6                                       |
| Canvas             | @xyflow/react (ReactFlow v12)                                        |
| Code Editing       | @monaco-editor/react                                                 |
| State Management   | zustand v5                                                           |
| Styling            | Tailwind CSS 4 + Custom CSS variable design system                   |
| Icons              | lucide-react                                                         |
| Backend            | Python 3.12+ / FastAPI / async                                       |
| Agent Framework    | DSPy v3.1+ (StreamingReAct — custom ReAct subclass)                  |
| Tool Sandbox       | Deno + Pyodide (via DSPy PythonInterpreter)                          |
| LLM Default        | Ollama (configurable: OpenAI, Anthropic, Groq via DSPy LM)           |
| Database           | PostgreSQL 17 + pgvector (async SQLAlchemy 2.0 + Alembic)            |
| Migrations         | Alembic (auto-generated, in `backend/alembic/versions/`)             |
| Streaming          | WebSocket for real-time agent event streaming                        |
| Memory             | mem0ai + Qdrant (local, per-agent vector store)                      |
| Observability      | MLflow DSPy autolog (`mlflow.dspy.autolog()`)                        |
| Testing (backend)  | pytest + pytest-asyncio + httpx (SQLite for test isolation)          |
| Testing (frontend) | vitest + @testing-library/react + msw                                |
| E2E Testing        | Playwright (Chromium, 1 worker, SQLite backend)                      |
| Container Runtime  | Docker + Docker Compose                                              |

---

## System Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│  REACT FRONTEND (localhost:5173)                                          │
│                                                                           │
│  ┌──────┐ ┌─────────────── CanvasView (ReactFlow) ────────────────────┐  │
│  │ Rail │ │                                                           │  │
│  │  Add │ │  ┌─[Agent A: worker]─┐  edges: tool_access/handoff   ──┐ │  │
│  │  Add │ │  │  name, role,      │──→  ┌─[Tool 1: Python code]──┐  │ │  │
│  │  Exp │ │  │  instructions,    │     │  def search(q): ...     │  │ │  │
│  │  Imp │ │  │  model            │     └─────────────────────────┘  │ │  │
│  │  Thm │ │       │handoff                                         │ │  │
│  │      │ │       ▼                                                │ │  │
│  │      │ │  ┌─[Agent B: router]─┐──→  ┌─[Agent C: worker]───┐    │ │  │
│  │      │ │  │  type=router      │     │                     │    │ │  │
│  │      │ │  │  handoff→Agent C  │     └─────────────────────┘    │ │  │
│  │      │ │  └───────────────────┘                                │ │  │
│  │      │ └───────────────────────────────────────────────────────┘ │  │
│  │      │                                                           │  │
│  │      │  ┌── PropertiesOverlay ──┐  ┌── ChatOverlay ──────────┐  │  │
│  │      │  │  AgentEditor          │  │  Conversation selector  │  │  │
│  │      │  │  ToolEditor (Monaco)  │  │  Messages (grouped)     │  │  │
│  │      │  └───────────────────────┘  │  Input + Send           │  │  │
│  │      │                             └─────────────────────────┘  │  │
│  │  ←───┤  TopBar (canvas name, save status, chat/obs toggle)      │  │
│  └──────┘                                                          │  │
│                                                                      │  │
│  HTTP REST + WebSocket ◄─────────────────────────────────────────►│  │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│  FASTAPI BACKEND (localhost:8000)                                      │
│                                                                        │
│  ┌────────────┐ ┌───────────────┐ ┌──────────────────────────┐       │
│  │ CanvasRepo │ │ CanvasRunner  │ │ StreamingReAct (DSPy)    │       │
│  │ ConvRepo   │ │  setup()      │ │  on_event(callback)      │       │
│  │ (async ORM)│ │  _build_tools │ │  aforward() → events     │       │
│  │            │ │  _build_agents│ │  ReAct loop:             │       │
│  │            │ │  run()        │ │   thought → tool → obs   │       │
│  │            │ │              │ │   ...until "finish"       │       │
│  │            │ │  MemoryProv.  │ └──────────────────────────┘       │
│  └────────────┘ └───────────────┘                                    │
│                      │                                                 │
│                      ▼                                                 │
│  ┌──────────────────────────┐                                          │
│  │ Sandbox (Deno/Pyodide)   │  ← All tool execution goes here           │
│  │  PythonInterpreter       │                                          │
│  │  singleton process       │                                          │
│  └──────────────────────────┘                                          │
│                                                                        │
│  Routes:                                      │
│  /api/canvases/**     — REST CRUD             │
│  /api/tools/inspect   — Tool metadata        │
│  /api/tools/test      — Tool test execution  │
│  /ws/conversations/{id}/run — WebSocket       │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│  POSTGRESQL (pgvector/pg17)   +   MLflow (localhost:5000)             │
│  canvases, agent_nodes, tool_nodes, edges    DSPy traces             │
│  conversations, messages                       (autolog)             │
│  mem0 → Qdrant (local vector store)                                │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Layout & UX Zones

The workspace is composed of these zones. All are positioned absolutely within a
full-screen `AppShell`.

| Zone | Component | Position | Size | Description |
|---|---|---|---|---|
| **TopBar** | `TopBar.tsx` | top, left=12 | h=40, spans canvas width | Canvas name, save status, observability/chat toggles |
| **SidebarRail** | `SidebarRail.tsx` | left | w=48, full height | Add agent/tool, clear, export/import, theme toggle |
| **CanvasView** | `CanvasView.tsx` | top=40, left=48 | fills remaining | ReactFlow canvas: agents, tools, edges |
| **PropertiesOverlay** | `PropertiesOverlay.tsx` | right | w=320 | AgentEditor or ToolEditor based on selection |
| **ChatOverlay** | `ChatOverlay.tsx` | right | w=400 | Conversation threads, message input, streaming output |
| **ObservabilityView** | `ObservabilityView.tsx` | full canvas | full area | Embedded MLflow iframe, replaces canvas entirely |

**Layout math** (`AppShell.tsx`):
```
canvasRightOffset = (chatOpen ? 400 : 0) + (propertiesOpen ? 320 : 0)
```

When overlays open, the canvas container shrinks and `fitView` re-centers nodes
(delayed 350ms to match the transition).

---

## Project Structure

```
mj-agent-framework/
├── README.md                 # Quick start, env vars, top-level overview
├── CLAUDE.md                 # AI/human developer context: where things live, recipes
├── CONTEXT.md                # Glossary of canonical terms
├── ARCHITECTURE.md           # ← YOU ARE HERE
├── CONTEXT.md                # Glossary of canonical terms
├── docker-compose.yml        # postgres + backend + frontend + mlflow
├── canvas_screen.png         # Screenshot for README
├── ollama_entrypoint.sh      # Ollama GPU entry point (commented out in compose)
│
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml        # Project config, dependencies, ruff settings
│   ├── alembic.ini           # Migration config
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/         # Auto-generated migration scripts
│   ├── .env                  # LLM_BASE_URL, LLM_MODEL, MLFLOW_TRACKING_URI, etc.
│   ├── .env.example          # Template for .env
│   ├── src/
│   │   └── canvas_server/
│   │       ├── __init__.py
│   │       ├── main.py            # FastAPI app, CORS, lifespan (MLflow + sandbox init)
│   │       ├── config.py          # pydantic-settings: DB, LLM, mem0, MLflow
│   │       ├── database.py        # Async engine, session factory, Base
│   │       ├── exceptions.py      # CanvasNotFoundError, ToolCompilationError, ToolExecutionError
│   │       ├── sandbox.py         # Singleton Deno/Pyodide sandbox (via DSPy PythonInterpreter)
│   │       ├── models/
│   │       │   ├── canvas.py      # SQLAlchemy ORM: Canvas, AgentNode, ToolNode, Edge, Conversation, Message
│   │       │   └── api.py         # Pydantic: request/response schemas
│   │       ├── repos/
│   │       │   ├── canvas_repo.py         # Async CRUD for canvases + nodes + edges
│   │       │   └── conversation_repo.py   # Async CRUD for conversations + messages
│   │       ├── routes/
│   │       │   ├── canvas.py      # REST: /api/canvases/**
│   │       │   ├── execute.py     # WebSocket: /ws/conversations/{id}/run
│   │       │   └── tools.py       # REST: /api/tools/inspect, /api/tools/test
│   │       ├── runner/            # Core execution engine package
│   │       │   ├── agent_factory.py # Builds DSPy agents from canvas nodes
│   │       │   ├── execution.py     # Executes individual worker agent runs
│   │       │   ├── rag_helper.py    # Chunking & in-memory DSPy embeddings search
│   │       │   └── runner.py        # CanvasRunner — orchestrates multi-agent flows
│   │       ├── streaming_react.py # StreamingReAct — DSPy ReAct subclass with event emission
│   │       ├── tool_factory.py    # Sandbox-based Python string → DSPy tool compilation + test execution
│   │       ├── memory_config.py   # mem0 config builder from settings
│   │       └── memory_provider.py # MemoryProvider — mem0 wrapper as DSPy tool functions
│   └── tests/
│       ├── conftest.py          # Fixtures: fresh_db, test_session, test_client, canvas fixtures
│       ├── test_runner.py       # CanvasRunner unit tests (mocked agents)
│       ├── test_conversations.py # Conversation API + repo + runner integration tests
│       ├── test_rag.py          # RAG utility, API endpoints, and runner integration tests
│       ├── test_config.py
│       ├── test_models_api.py
│       ├── test_repos.py
│       ├── test_routes_canvas.py
│       ├── test_routes_tools.py # Tool inspect + test API endpoints
│       ├── test_tool_factory.py # Tool compilation, inspection, execution, type coercion
│       ├── test_sandbox_docker.py # Sandbox manager lifecycle + session execution
│       └── test_e2e.py          # Full-stack E2E (canvas CRUD via test client)
│
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.ts           # Vite config: React, Tailwind, @ alias, MLflow proxy
│   ├── vitest.config.ts         # Test config: jsdom, globals, coverage thresholds
│   ├── tsconfig.json
│   ├── tsconfig.app.json
│   ├── playwright.config.ts     # E2E: starts backend + frontend, SQLite for CI
│   ├── index.html
│   ├── e2e/
│   │   ├── canvas-nodes.spec.ts
│   │   ├── canvas-toolbar.spec.ts
│   │   ├── canvas.spec.ts
│   │   ├── chat-panel.spec.ts
│   │   ├── fixtures.smoke.spec.ts
│   │   └── properties-sidebar.spec.ts
│   │   └── tool-editor.spec.ts
│   └── src/
│       ├── main.tsx
│       ├── App.tsx               # Landing page OR AppShell (based on canvasId)
│       ├── types/
│       │   └── index.ts          # AgentNodeData, ToolNodeData, ExecutionEvent, API types
│       ├── store/
│       │   ├── canvasStore.ts    # zustand: nodes, edges, selection, execution state, viewport
│       │   └── themeStore.ts     # zustand: dark/light, localStorage persistence
│       ├── lib/
│       │   └── api.ts            # fetch wrappers for all REST endpoints
│       ├── hooks/
│       │   ├── useCanvasPersistence.ts  # Debounced auto-save (500ms) to backend
│       │   └── useCanvasPersistence.test.ts
│       ├── components/
│       │   ├── canvas/
│       │   │   ├── CanvasView.tsx    # ReactFlow container, edge validation, viewport tracking
│       │   │   ├── AgentNode.tsx     # Custom node: name, type badge, role/instructions, glow on active
│       │   │   ├── ToolNode.tsx      # Custom node: name, code preview (first 3 lines)
│       │   │   └── CustomEdge.tsx    # Bezier edge, hover-to-delete button, dashed for handoff
│       │   ├── layout/
│       │   │   ├── AppShell.tsx       # Root layout: zones composited with absolute positioning
│       │   │   ├── TopBar.tsx         # Canvas name input, save status, toggle buttons
│       │   │   ├── SidebarRail.tsx    # Left icon rail: add agent/tool, import/export, theme
│       │   │   ├── RailItem.tsx       # Single rail button (icon, label, active/danger states)
│       │   │   ├── RailPopover.tsx    # Popover anchored to rail item, click-outside closes
│       │   │   └── OverlayPanel.tsx   # Slide-in panel with enter/exit animations, Escape to close
│       │   ├── sidebar/
│       │   │   ├── AgentEditor.tsx    # Agent properties: type, name, role, instructions, model, memory, history
│       │   │   ├── ToolEditor.tsx     # Monaco Python editor, tool name, inferred args preview
│       │   │   └── ...test.tsx       # Corresponding tests
│       │   ├── chat/
│       │   │   └── ChatOverlay.tsx    # Conversation list, messages, WebSocket connect, turn grouping
│       │   ├── observability/
│       │   │   └── ObservabilityView.tsx  # MLflow iframe
│       │   ├── PropertiesOverlay.tsx  # Dispatches to AgentEditor or ToolEditor based on selection
│       │   └── ThemeToggle.tsx
│       ├── styles/
│       │   └── globals.css           # Design system: CSS variables, utility classes, animations
│       └── test/
│           ├── setup.ts
│           └── mocks/
│               ├── handlers.ts       # MSW request handlers
│               ├── monaco.ts         # Monaco editor mock
│               ├── server.ts         # MSW server setup
│               └── websocket.ts      # WebSocket mock
│
├── mlflow/
│   └── Dockerfile
│
└── docs/
    └── adr/
        └── 0001-frontend-test-framework.md
```

---

## Database Schema

The database uses PostgreSQL 17 with pgvector. Alembic manages migrations.

```
canvases
├── id: UUID PK (default gen_random_uuid())
├── name: VARCHAR(255) DEFAULT 'Untitled Canvas'
├── created_at: TIMESTAMPTZ (default now())
├── updated_at: TIMESTAMPTZ (default now(), onupdate)
└── relationships: agent_nodes, tool_nodes, edges, conversations (CASCADE delete)

agent_nodes
├── id: UUID PK
├── canvas_id: UUID FK → canvases.id (CASCADE)
├── name: VARCHAR(255) DEFAULT 'Agent'
├── role: TEXT DEFAULT ''
├── instructions: TEXT DEFAULT ''
├── model_name: VARCHAR(255) DEFAULT 'ollama:llama3.1'
├── agent_type: VARCHAR(20) DEFAULT 'worker'       -- 'worker' | 'router'
├── enable_memory: BOOLEAN DEFAULT FALSE
├── enable_conversation_history: BOOLEAN DEFAULT FALSE
├── enable_rag: BOOLEAN DEFAULT FALSE
├── rag_chunk_size: INTEGER DEFAULT 1000
├── position_x: DOUBLE PRECISION DEFAULT 0
├── position_y: DOUBLE PRECISION DEFAULT 0
├── relationships: documents (CASCADE delete)
└── INDEX: idx_agent_nodes_canvas (canvas_id)

agent_documents
├── id: UUID PK
├── canvas_id: UUID FK → canvases.id (CASCADE)
├── agent_node_id: UUID FK → agent_nodes.id (CASCADE)
├── name: VARCHAR(255)
├── content: TEXT
├── created_at: TIMESTAMPTZ
├── INDEX: idx_agent_documents_canvas (canvas_id)
└── INDEX: idx_agent_documents_agent (agent_node_id)

tool_nodes
├── id: UUID PK
├── canvas_id: UUID FK → canvases.id (CASCADE)
├── name: VARCHAR(255) DEFAULT 'Tool'
├── code: TEXT DEFAULT ''
├── args: JSON DEFAULT []        -- inferred tool arguments
├── position_x: DOUBLE PRECISION DEFAULT 0
├── position_y: DOUBLE PRECISION DEFAULT 0
└── INDEX: idx_tool_nodes_canvas (canvas_id)

edges
├── id: UUID PK
├── canvas_id: UUID FK → canvases.id (CASCADE)
├── source_node_id: UUID        -- can reference agent_nodes.id or tool_nodes.id
├── target_node_id: UUID        -- can reference agent_nodes.id or tool_nodes.id
├── edge_type: VARCHAR(20)      -- 'tool_access' | 'handoff'
└── INDEX: idx_edges_canvas (canvas_id)

conversations
├── id: UUID PK
├── canvas_id: UUID FK → canvases.id (CASCADE)
├── name: VARCHAR(255) DEFAULT 'New Conversation'
├── status: VARCHAR(20) DEFAULT 'active'  -- 'active' | 'completed'
├── created_at: TIMESTAMPTZ
├── updated_at: TIMESTAMPTZ
└── relationships: messages (CASCADE delete)

messages
├── id: UUID PK
├── conversation_id: UUID FK → conversations.id (CASCADE)
├── role: VARCHAR(10)               -- 'user' | 'assistant' | 'system'
├── content: TEXT DEFAULT ''
├── agent_name: VARCHAR(255) NULL   -- populated for assistant messages
├── node_id: UUID NULL              -- agent node that produced this message
├── event_type: VARCHAR(30) NULL    -- 'run_start' | 'final_answer' | 'thought' | 'error' | etc.
├── created_at: TIMESTAMPTZ
└── INDEX: idx_messages_conversation (conversation_id)
```

**Key schema decisions:**
- No FK constraints on `source_node_id` / `target_node_id` in `edges` — they can reference either `agent_nodes` or `tool_nodes`
- `messages.event_type` mirrors the WebSocket event type for traceability
- Conversations stay `'active'` across multi-turn exchanges; never set to `'completed'` in `runner.py`

---

## API Endpoints

### Canvas CRUD

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/canvases` | Create new canvas (empty) |
| `GET` | `/api/canvases` | List all canvases (name + id + timestamps) |
| `GET` | `/api/canvases/{id}` | Full canvas with nodes and edges |
| `PUT` | `/api/canvases/{id}` | Save/replace nodes and edges (delete+insert) |
| `DELETE` | `/api/canvases/{id}` | Delete canvas and all related data |
| `GET` | `/api/canvases/{id}/export` | Download canvas as JSON file |
| `GET` | `/api/canvases/{id}/export-zip` | Download canvas as ZIP package with manifest and RAG documents |
| `POST` | `/api/canvases/import` | Import canvas from JSON payload |
| `POST` | `/api/canvases/import-zip` | Import canvas from a ZIP package with manifest and document files |

### Document Upload / RAG API (scoped under canvas & agent)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/canvases/{id}/agents/{agent_id}/documents` | List uploaded RAG documents for the agent |
| `POST` | `/api/canvases/{id}/agents/{agent_id}/documents` | Upload a new text document (multipart/form-data) |
| `DELETE` | `/api/canvases/{id}/agents/{agent_id}/documents/{doc_id}` | Delete a document |

### ZIP import/export format

`/api/canvases/{id}/export-zip` produces a ZIP archive containing:
- `manifest.json` — canvas metadata, nodes, edges, and document metadata
- `documents/{agent_id}/{doc_id}.txt` — raw text content for each uploaded RAG document

`/api/canvases/import-zip` reads the manifest and reconstructs the canvas, remapping IDs as needed and importing documents into their target agents.

Example ZIP manifest structure:

```json
{
  "name": "Demo Team",
  "nodes": {
    "agents": [
      {
        "id": "5c2a7c1a-6f3a-4e31-b8d3-4d3d4255e4a2",
        "name": "SupportAgent",
        "role": "You are a customer support agent.",
        "instructions": "Answer questions using the provided docs.",
        "model_name": "ollama_chat/gemma4:31b",
        "agent_type": "worker",
        "enable_memory": false,
        "enable_conversation_history": false,
        "enable_rag": true,
        "rag_chunk_size": 1000,
        "position_x": 120,
        "position_y": 100
      }
    ],
    "tools": [],
  },
  "edges": [],
  "documents": [
    {
      "id": "7b4a1c6f-3a9d-4c65-8a77-5d2b1e4f6c9d",
      "agent_node_id": "5c2a7c1a-6f3a-4e31-b8d3-4d3d4255e4a2",
      "name": "support_faq.txt",
      "created_at": "2026-06-08T15:00:00Z",
      "path": "documents/5c2a7c1a-6f3a-4e31-b8d3-4d3d4255e4a2/7b4a1c6f-3a9d-4c65-8a77-5d2b1e4f6c9d.txt"
    }
  ]
}
```

The ZIP archive also contains the referenced document file at:

```
documents/{agent_id}/{document_id}.txt
```

### Conversation API (scoped under canvas)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/canvases/{id}/conversations` | Create conversation |
| `GET` | `/api/canvases/{id}/conversations` | List conversations |
| `GET` | `/api/canvases/{id}/conversations/{cid}` | Get conversation with messages |
| `DELETE` | `/api/canvases/{id}/conversations/{cid}` | Delete conversation |

### Execution

| Method | Path | Description |
|---|---|---|
| `WS` | `/ws/conversations/{conversation_id}/run` | WebSocket: send `{"prompt":"..."}`, receive events |

### Tool Testing (stateless — no DB session required)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/tools/inspect` | Extract function name, arguments, type hints, defaults from Python code |
| `POST` | `/api/tools/test` | Execute tool function in sandbox with user-provided string args |

### PUT `/api/canvases/{id}` — Request Body

```json
{
  "name": "My Workflow",
  "nodes": {
    "agents": [{
      "id": "uuid",
      "name": "Researcher",
      "role": "You are a research assistant.",
      "instructions": "Look up facts and provide citations.",
      "model_name": "ollama_chat/gemma4:31b",
      "agent_type": "worker",
      "enable_memory": false,
      "enable_conversation_history": false,
      "enable_rag": false,
      "rag_chunk_size": 1000,
      "position_x": 100,
      "position_y": 200
    }],
    "tools": [{
      "id": "uuid",
      "name": "DatabaseLookup",
      "code": "def search(query: str) -> str:\n    ...",
      "position_x": 400,
      "position_y": 200
    }]
  },
  "edges": [{
    "id": "uuid",
    "source_node_id": "agent-uuid",
    "target_node_id": "tool-uuid",
    "edge_type": "tool_access"
  }]
}
```

The save operation performs a delta-sync (upsert) for agent nodes to preserve child relationships (such as agent documents), and uses a transaction to ensure atomicity. Tool nodes and edges are replaced atomically (delete-all → insert-all). `id` fields are client-generated and preserved across saves.

---

## WebSocket Wire Protocol

### Endpoint

```
ws://localhost:8000/ws/conversations/{conversation_id}/run
```

### Flow

1. Client connects WebSocket
2. Client sends `{"prompt": "..."}` (within 30s timeout)
3. Server streams events as newline-delimited JSON
4. Server closes connection on completion or error

### Events

All events carry `node_id` (the agent node that produced them) except `run_start`,
`run_complete`, and `error`.

```json
// Run lifecycle
{"type": "run_start", "canvas_id": "550e8400-e29b-41d4-a716-446655440000"}

// Agent activation
{"type": "agent_start", "agent": "Researcher", "agentType": "worker", "node_id": "..."}

// Reasoning (from StreamingReAct loop)
{"type": "thought", "agent": "Researcher", "content": "I need to query the database.", "node_id": "..."}

// Tool usage (from StreamingReAct loop)
{"type": "tool_start", "agent": "Researcher", "tool": "DatabaseLookup", "node_id": "..."}
{"type": "tool_result", "agent": "Researcher", "tool": "DatabaseLookup", "output": "[...]", "node_id": "..."}

// Handoff between agents (from runner)
{"type": "handoff", "from": "Orchestrator", "to": "WeatherAgent", "node_id": "..."}

// Final answer
{"type": "final_answer", "agent": "Researcher", "content": "The weather will be sunny.", "node_id": "..."}

// Completion
{"type": "run_complete", "result": "Workflow execution completed."}

// Error
{"type": "error", "message": "Tool 'Lookup' timed out.", "agent": "Researcher", "node_id": "..."}
```

**Note on `tool_start` vs `tool_call`**: The frontend event types index says
`tool_call` but the runner emits `tool_start` (via `StreamingReAct`). These are
synonyms — the frontend `ChatOverlay.tsx` handles both in its `onmessage` handler,
but only `tool_result` is used for display. The TS `ExecutionEvent` union includes
`tool_call` as forward-compatible.

---

## Backend Architecture

### config.py

`pydantic-settings` class `Settings` reads from `.env`:

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://...` | Async DB connection |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | Allowed origins |
| `LLM_BASE_URL` | `http://192.168.1.120:11434` | Ollama server URL |
| `LLM_MODEL` | `ollama_chat/gemma4:31b` | Default model |
| `MEM0_LLM_PROVIDER` | `ollama` | mem0 LLM backend |
| `MEM0_LLM_MODEL` | `gemma4:31b` | mem0 LLM model |
| `MEM0_EMBEDDER_PROVIDER` | `ollama` | Embedding backend |
| `MEM0_EMBEDDER_MODEL` | `nomic-embed-text` | Embedding model |
| `MLFLOW_ENABLED` | `True` | Enable/disable MLflow init |
| `MLFLOW_TRACKING_URI` | `http://mlflow:5000` | MLflow server |
| `MLFLOW_EXPERIMENT_NAME` | `canvas-agents` | MLflow experiment |

### models/canvas.py — SQLAlchemy ORM

Six tables: `Canvas`, `AgentNode`, `ToolNode`, `Edge`, `Conversation`, `Message`.
All relationships cascade delete. `Edge.source_node_id` / `target_node_id` are
UUIDs without FK constraints (can point to agent or tool nodes).

### models/api.py — Pydantic Schemas

Input models: `AgentNodeInput`, `ToolNodeInput`, `EdgeInput`, `CanvasSaveRequest`.
Response models: `CanvasResponse`, `ConversationResponse`, `MessageResponse`.
The `CanvasResponse` nests `CanvasNodesInput` (agents + tools) + edges.

Key fields on `AgentNodeInput`: `agent_type`, `enable_memory`, `enable_conversation_history`.

### database.py — Engine & Session

Singleton engine, thread-safe session factory. Key features:
- `reset_session_factory()` — used by tests between test runs
- `get_session()` — FastAPI dependency that yields async sessions
- SQLAlchemy `Base` declarative base for all ORM models

### repos/canvas_repo.py — Canvas CRUD

`CanvasRepo` methods:
- `create()` / `create_full()` / `get()` / `get_or_404()` / `list_all()` / `delete()`
- `save_nodes_and_edges()` — deletes all existing nodes/edges, inserts replacements
- `create_full()` — used by import, remaps IDs to avoid collisions
- All queries use `selectinload` for eager loading of all relations

### repos/conversation_repo.py — Conversation CRUD

`ConversationRepo` methods:
- `create()` / `get()` / `get_or_404()` / `delete()` / `list_for_canvas()`
- `add_message()` — appends a message, updates conversation `updated_at`
- `complete_conversation()` — sets status to "completed" (used by frontend)

### routes/canvas.py — REST Router

Maps CRUD operations to FastAPI endpoints. Key patterns:
- `_canvas_to_response()` helper converts ORM → Pydantic consistently
- Export returns a `Response` with `Content-Disposition: attachment`
- Import uses `create_full()` with ID remapping

### routes/execute.py — WebSocket Router

Single endpoint `run_conversation()`:
1. Accepts WebSocket
2. Receives `{"prompt", "target_agent_id?"}` within 30s timeout
3. Creates `CanvasRunner` with conversation repo
4. Calls `runner.run()` in a background task
5. Commits session on completion (critical — messages otherwise lost on rollback)

---

## Execution Engine

### runner.py — CanvasRunner

The core orchestrator. See [Agent Execution Model](#agent-execution-model) below
for the detailed agent types, and [Conversation Lifecycle](#conversation-lifecycle)
for history management.

**Initialization:**
```
CanvasRunner(canvas, conversation_repo=None, conversation_id=None)
  ├── tools: dict[uuid.UUID, callable]     — compiled tool functions
  ├── agents: dict[uuid.UUID, StreamingReAct] — built agent instances
  ├── node_map: dict[uuid.UUID, agent_node]   — lookup by ID
  ├── _wired_agents: set[uuid.UUID]         — agents with event callbacks attached
  ├── _memory_providers: dict[uuid.UUID, MemoryProvider]
  └── _shared_memory: mem0.Memory | None
```

**`setup()` — Lazy Initialization:**
1. Build `node_map` from `canvas.agent_nodes`
2. `_build_tools()` — compile all `ToolNode.code` strings via `tool_factory`
3. `_build_agents()` — build only **worker** agents (routers are deferred)

**`run()` — Workflow Execution:**

```
run(user_prompt, send_event, target_agent_id=None)
  ├── setup() (if not already called)
  ├── run_start event
  ├── load conversation history from DB
  ├── build dspy.History if conversation history enabled
  ├── WITH dspy.context(lm=...):
  │   ├── if target_agent_id is specified:
  │   │   ├── if router → build router agent → run → persist answer
  │   │   └── if worker → run worker → persist answer
  │   ├── else (no target):
  │   │   ├── if first agent is router → run as router
  │   │   └── else → sequential worker chain via handoff edges
  │   ├── append turn to dspy.History
  │   └── auto-store memory for primary agent (if enabled)
  └── run_complete event
```

### tool_factory.py — Sandbox-Based Tool Compilation & Execution

```python
async def compile_tool_from_code(name: str, code: str, dependencies: list[str] | None = None) -> callable:
    # 1. Validate syntax via sandbox (Deno/Pyodide)
    # 2. Extract function metadata on host side (exec for metadata only)
    # 3. Return async wrapper that calls the function in the sandbox
    #    — wrapper preserves __name__, __doc__, __annotations__ for DSPy
    #    — wrapper handles `pip install` for specified dependencies


async def inspect_tool_code(name, code) -> ToolInspectResponse:
    # Extract function name, parameter names, type hints, default values
    # Uses host-side exec for inspect.signature (no execution)

async def execute_tool_code(name, code, args) -> ToolTestResponse:
    # Compile code, coerce string args to Python types, execute in sandbox
    # Returns {success, output, execution_time_ms}

def coerce_arg(value: str, type_hint: str) -> Any:
    # Coerce string → int, float, bool, list, dict (via type hints)
```

**Sandbox model:** All tool execution (both agent runs and interactive testing)
goes through the Deno/Pyodide sandbox (`canvas_server.sandbox.Sandbox`). The
sandbox is a long-lived Deno subprocess running Pyodide (WASM Python), started
at app startup and kept warm. Host-side `exec()` is used **only** for extracting
function metadata (name, docstring, annotations) that DSPy needs — never for
execution.

**Security:** The sandbox has no access to the host filesystem, network, or
environment variables by default (Deno permission model). See ADR-0002.

### streaming_react.py — StreamingReAct

```python
class StreamingReAct(dspy.ReAct):
    """DSPy ReAct subclass that emits events per iteration."""

    def on_event(self, callback):
        """Register async callback accepting dict event."""

    async def aforward(self, **input_args):
        # For each ReAct iteration:
        #   1. Emit "thought"
        #   2. If next_tool == "finish" → break
        #   3. Emit "tool_start"
        #   4. Call tool, emit "tool_result"
        # Extract final answer from trajectory
```

Key detail: The `runner.py` wraps the `callback` to inject `agent` and `node_id`
before forwarding to the WebSocket, AND to emit a second `tool_start` event with
the tool node's `node_id` for canvas highlighting.

---

## Agent Execution Model

### Two Agent Types

| Type | Built When | Can Have Tools? | Can Handoff? | Use Case |
|---|---|---|---|---|
| `worker` | During `setup()` | Yes | No | Execute specific tasks (search, compute, API calls) |
| `router` | Lazily at run time (`_build_router_agent()`) | Yes | Yes | Orchestrate: route tasks to sub-agents via handoff |

### Worker Agents

Workers are `StreamingReAct` instances built during `setup()`. They:
- Receive a DSPy signature with `user_request` (and optionally `history`)
- ReAct-loop through tools (thought → tool → observation → ... → finish)
- Cannot hand off — they produce a final answer
- **RAG Support**: If `enable_rag` is True, their instructions and role undergo templating. The `{{ rag_document }}` placeholder is replaced by the retrieved passages from the RAG search. This is built dynamically on every run/handoff turn.

### Router Agents

Routers are built lazily when first invoked by `_make_handoff_tool()` or directly
by `run()`. They:
- Have signature + tools (from tool_access edges)
- Have `HandoffTool` function(s) created by `_make_handoff_tool()`
- The handoff tool is a plain async function `transfer_to_{target_name}(task: str) -> str`
- Router delegates to sub-agent, collects result, and returns it as tool output
- Sub-agents can be workers or other routers (deferred lookup pattern)

### Handoff Chain (No Target Agent)

When `run()` is called without `target_agent_id` and the first agent is a worker:

```
current_agent = first worker in list
while current_agent is not None and not visited:
    run worker → get final_answer
    pick first handoff edge as next_agent
    emit handoff event
```

This creates a simple sequential chain. This is the **legacy execution path** —
the primary use is now `target_agent_id` with a router node.

### Target Agent Mode

When `target_agent_id` is specified (sent from frontend):
- If agent type is `router`: build the router agent with handoff tools, run it
- If agent type is `worker`: attach events, run the worker directly

This is the **primary execution path** — the frontend always sends `target_agent_id`.

### Event Callback Wiring

The `_attach_events()` method wraps the raw callback from `StreamingReAct`:
```
raw callback → runner wraps it → sends to WebSocket
    ├── adds agent name + node_id to every event
    └── for tool_start events: also emits tool_start with tool node's node_id
```

Tool node ID is resolved via `_tool_name_to_id` map (built during `_build_tools`).

### Edge Validation Rules

| Source | Target | Allowed? | Edge Type |
|---|---|---|---|
| Agent | Tool | Yes | `tool_access` |
| Agent | Agent | Yes | `handoff` |
| Tool | Tool | No | — |
| Tool | Agent | No | — |

Enforced on frontend (`isValidConnection` in `CanvasView.tsx`) and implicitly
on backend (edge validation happens during graph traversal, not as explicit checks).

---

## Memory Architecture

### mem0 + Qdrant

Memory is powered by [mem0ai](https://mem0.ai/) with a local Qdrant vector store.

**Configuration** (`memory_config.py`):
```python
{
    "llm": {"provider": "ollama", "config": {"model": "gemma4:31b"}},
    "embedder": {"provider": "ollama", "config": {"model": "nomic-embed-text"}},
    "vector_store": {"provider": "qdrant", "config": {"embedding_model_dims": 768}},
    "version": "v1.1",
}
```

### Shared Memory Instance

All agents share a single `mem0.Memory` instance to avoid file-locking issues
with the local Qdrant client. Each agent gets its own `MemoryProvider` with a
distinct `user_id = f"agent_{agent_node.id}"` for isolation.

### MemoryProvider

Three DSPy-compatible tool functions per agent (when `enable_memory=True`):

| Tool | Description |
|---|---|
| `memory_search(query)` | Semantic search over stored memories (top 5) |
| `memory_store(content)` | Persist a fact or preference |
| `memory_get_all()` | Retrieve all stored memories |

**Auto-store**: After each `run()`, the runner stores `"The user asked: '{prompt}' → Response: {answer}"` for the primary agent, providing a fallback audit trail even if the LLM forgets to call `store_memory` explicitly.

---

## Conversation Lifecycle

### Persistence

Conversations are persisted across WebSocket connections:
1. Frontend creates a `conversation` via REST API
2. Each user message → backend persists as `Message(role="user", event_type="run_start")`
3. Each final answer → backend persists as `Message(role="assistant", event_type="final_answer")`
4. Session is committed explicitly in `routes/execute.py` — otherwise the context
   manager rolls back on close, losing all messages

### Multi-Turn History

When `enable_conversation_history` is enabled on an agent:
1. Previous messages are loaded from DB on `run()`
2. A `dspy.History` object is built containing only user/assistant pairs from
   history-enabled agents (system prompts and sub-agent responses excluded)
3. The `dspy.History` is passed to the agent's `aforward()` via the `history` field
4. The DSPy signature includes `history: dspy.History = dspy.InputField()`
5. Agent sees prior turns as context for the current query

### History Filtering Rules

From `_format_history()` and `dspy.History` construction:
- **System prompts** (role="system") → excluded (already in DSPy signature instructions)
- **User messages** → always included
- **Assistant messages** → only included if the agent has `enable_conversation_history=True`
- **Intermediate sub-agent responses** → excluded (only final answers from history-enabled agents)
- **Separator** `---` between messages

### Conversation Status

Conversations have `status: "active" | "completed"`.
- Stay `"active"` across multiple turns (never set to `"completed"` by `runner.run()`)
- Set to `"completed"` explicitly by the frontend or via `complete_conversation()` in repo

---

## Frontend Architecture

### App Shell & Layout

The UI has two main modes:

1. **Landing Page** (`App.tsx` when `canvasId === null`):
   - "Agent Builder" branding
   - "New Canvas" button → creates canvas via API
   - Recent canvases list (loaded from API)
   - Deep-link support: `?canvas=<id>` URL parameter

2. **AppShell** (`App.tsx` when `canvasId !== null`):
   - Absolute-positioned zones (see [Layout & UX Zones](#layout--ux-zones))
   - CanvasView receives shrinking right edge when overlays open
   - ObservabilityView replaces all canvas zones when toggled

### State Management (zustand)

**canvasStore.ts:**
```typescript
interface CanvasStore {
  canvasId: string | null;
  canvasName: string;
  nodes: Node[];          // ReactFlow Node array
  edges: Edge[];          // ReactFlow Edge array
  selectedNodeId: string | null;
  activeNodeId: string | null;  // Node highlighted during execution
  chatOpen: boolean;
  observabilityOpen: boolean;
  saveStatus: "idle" | "saving" | "saved" | "error";
  viewport: { x, y, zoom };
  // + setters for each field
}
```

**themeStore.ts:**
```typescript
interface ThemeState {
  theme: "dark" | "light";
  toggleTheme: () => void;
  setTheme: (theme) => void;
}
// Initial: checks localStorage → matchMedia → default "dark"
// Persists to localStorage key "agent-builder-theme"
// Theme transitions with 400ms CSS animation
```

### Canvas View

**CanvasView.tsx** — ReactFlow container:
- Renders `nodeTypes = { agent: AgentNode, tool: ToolNode }`
- Renders `edgeTypes = { default: CustomEdge }`
- Edge validation via `isValidConnection()`:
  - agent→tool = valid (tool_access)
  - agent→agent = valid (handoff)
  - all others = invalid
- New edges automatically typed: agent→agent = handoff, else tool_access
- Handoffs rendered with `strokeDasharray: "6 4"`
- Auto `fitView` when overlays open/close (300ms transition + 350ms delay)
- Tracks viewport for "add at center" calculation

**AgentNode.tsx** — Custom node:
- Header with icon (Brain for worker, GitBranch for router) + name + type badge
- Body shows role (2 lines) + instructions (4 lines)
- Active state: green `animate-pulse` border + glow
- Selected state: teal border + glow
- Resizable via `NodeResizer`
- Settings button opens PropertiesOverlay

**ToolNode.tsx** — Custom node:
- Header with Wrench icon + name
- Body shows first 3 lines of Python code as preview
- Same active/selected state pattern as AgentNode

**CustomEdge.tsx** — Bezier edge:
- Hover to reveal delete (X) button
- Handoff edges: purple dasharray, lower opacity
- Tool access edges: subtle gray

### Overlay Panels

**OverlayPanel.tsx** — Generic slide-in panel:
- Enter animation: `overlaySlideIn` (250ms cubic-bezier)
- Exit animation: `overlaySlideOut` (200ms cubic-bezier)
- Closes on Escape key
- Accepts `width` and `offsetRight` props (for stacking Properties + Chat)

**PropertiesOverlay.tsx** — Right panel (w-320):
- Shows `AgentEditor` or `ToolEditor` based on selected node type
- Sits to the left of ChatOverlay when both open

**ChatOverlay.tsx** — Right panel (w-400):
- Conversation selector dropdown (create, switch, delete)
- Message display grouped into "turns" per user message
- Turn structure: user message → collapsible steps (thoughts, handoffs, tool results) → final answer
- Streaming: incoming WebSocket events rendered as they arrive (steps shown live)
- Input bar with send/stop button
- WebSocket lifecycle: connect on send, close on complete/error

### Auto-Save

`useCanvasPersistence()` hook:
- Debounces 500ms after nodes/edges/name change
- Serializes to `CanvasSavePayload` format
- PUTs to `/api/canvases/{id}`
- Shows save status in TopBar (saving/saved/error)
- Maintains a serialized JSON ref to skip unchanged saves
- Status auto-resets to idle after 3s

### ObservabilityView

When toggled, the entire canvas area is replaced with an iframe loading:
- URL: `/mlflow/` (Vite-proxied to `http://mlflow:5000`)
- Proxied through Vite dev server so same-origin iframe works (no X-Frame-Options issue)

---

## CSS Design System & Theming

### CSS Variables

All colors are CSS custom properties, defined in `globals.css` with `@theme`
(inline via Tailwind v4's `@theme` at-rule) and overridden per theme.

**Dark theme** (default):
- Base: `#09090b`, Surface: `#131316`, Elevated: `#1c1c22`
- Accent: `#14b8a6` (teal for primary actions)
- Secondary: `#f59e0b` (amber for tools)
- Agent: `#8b5cf6` (purple for router agents)
- Semantic: success=green, danger=red, info=blue

**Light theme** (`html[data-theme="light"]`):
- Same variable names, adjusted for light background
- Base: `#f7f7f9`, Surface: `#ffffff`
- Accent: `#0d9488`, Secondary: `#d97706`, Agent: `#7c3aed`

### Key Utility Classes

Defined in `globals.css`:
- `.chrome-glass` — frosted glass for TopBar/SidebarRail
- `.rail-item` / `.rail-item-danger` / `.rail-item-active` — sidebar buttons
- `.rail-popover` — anchored popover with shadow
- `.input-base` — text input fields
- `.btn-primary` / `.btn-secondary` / `.btn-ghost` / `.btn-danger-ghost`
- `.glow-accent` / `.glow-secondary` / `.glow-danger` — node glow effects
- `.noise-bg` — SVG noise texture overlay for landing page
- `.overlay-panel` / `.overlay-panel-exit` — slide-in/out panels
- `.save-indicator-saving` — pulsing save icon

### Animations

| Animation | Purpose |
|---|---|
| `fadeIn` | Landing page elements (0.6s) |
| `staggerFadeIn` | Chat messages (0.3s staggered) |
| `dotPulse` | Loading/streaming indicator (1.2s) |
| `overlaySlideIn` | Panel open (250ms cubic-bezier) |
| `overlaySlideOut` | Panel close (200ms cubic-bezier) |
| `popoverIn` | Rail popover open (150ms) |
| `pulseRing` | Node selection highlight |
| `savePulse` | Saving indicator (1.5s) |
| `theme-transition` | Class on `<html>` during theme switch (400ms) |

---

## Docker & Deployment

### docker-compose.yml

Four services connect to a shared `agent_network`:

| Service | Port | Dependencies | Notes |
|---|---|---|---|
| `postgres` | 5432 | — | pgvector/pgvector:pg17, health check |
| `backend` | 8000 | postgres (health) | Hot-reload via `develop.watch`, mounts `./backend/src` |
| `frontend` | 5173 | backend | Hot-reload, Vite dev server |
| `mlflow` | 5000 | — | Custom Dockerfile, health check |

**Key details:**
- `extra_hosts: host.docker.internal:host-gateway` on backend — allows connecting
  to Ollama on the host machine
- MLflow proxy: Vite config proxies `/mlflow` to `http://mlflow:5000`
- Ollama service commented out (user runs Ollama on host or external server)
- Backend loads `.env` via `env_file`

### backend/Dockerfile

```dockerfile
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Install curl and Deno for sandboxed Python execution (Pyodide/WASM via DSPy PythonInterpreter)
RUN apt-get update && apt-get install -y curl unzip && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://deno.land/install.sh | sh && \
    mv /root/.deno/bin/deno /usr/local/bin/deno && \
    chmod +x /usr/local/bin/deno

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-install-project --no-dev
COPY alembic.ini .
COPY alembic/ alembic/
COPY src/ src/
ENV PYTHONPATH=/app/src
EXPOSE 8000
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn canvas_server.main:app --host 0.0.0.0 --port 8000 --reload"]
```

### frontend/Dockerfile

```dockerfile
FROM node:22-alpine
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

### Commands

```bash
# Full stack (requires Ollama on host):
docker compose up

# Backend + database only (API testing):
docker compose up postgres backend

# Run database migrations:
docker compose exec backend alembic upgrade head

# Run backend tests:
cd backend && uv run pytest -v

# Run frontend tests:
cd frontend && npx vitest run

# Run E2E tests:
cd frontend && npm run test:e2e
```

---

## Observability

MLflow DSPy autolog is initialized during server startup in `main.py`:

```python
mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
mlflow.set_experiment(settings.mlflow_experiment_name)
mlflow.dspy.autolog()
```

This captures:
- All agent calls and their ReAct trajectories
- Tool invocations (function name, input, output)
- LLM interactions (prompt, response, token count)
- Span tree with CHAIN type for full runs

The runner decorates the main `run()` method with `@mlflow.trace()` for top-level
span grouping.

**Configuration:**
- Disable in CI: `MLFLOW_ENABLED=false`
- Server startup tries gracefully and logs a warning if MLflow unreachable
- Embedded in frontend via iframe proxied through Vite

---

## Testing Architecture

### Backend Tests (`backend/tests/`)

| File | What It Tests |
|---|---|
| `conftest.py` | Fixtures: `fresh_db` (SQLite), `test_session`, `test_client`, `blank_canvas`, `canvas_with_nodes` |
| `test_runner.py` | `CanvasRunner` with mocked DSPy agents — event emission, setup, router→worker flow |
| `test_conversations.py` | Conversation CRUD API, repo operations, runner+conversation integration |
| `test_routes_canvas.py` | Canvas CRUD API endpoints |
| `test_routes_tools.py` | Tool inspect + test API endpoints (`@requires_docker`) |
| `test_tool_factory.py` | Tool compilation, inspection, execution, type coercion; sandbox integration tests (`@requires_docker`) |
| `test_sandbox_docker.py` | Sandbox manager lifecycle + session execution (`@requires_docker`) |
| `test_config.py` | Settings loading |
| `test_models_api.py` | Pydantic model serialization |
| `test_repos.py` | CanvasRepo operations (create, save, delete) |
| `test_e2e.py` | Full end-to-end: create canvas → add nodes → save → retrieve → delete |

**Key patterns:**
- Tests use SQLite via `TEST_DATABASE_URL` env var (or default `sqlite+aiosqlite:///test.db`)
- Each test gets a fresh database via `fresh_db` fixture (drop_all → create_all)
- Agent execution is mocked — no real LLM calls in tests
- `FakeCanvas`, `FakeAgentNode`, `FakeEdge` classes simplify test setup
- Sandbox tests use `@requires_docker` marker (`pytest.mark.skipif(not shutil.which("docker"))`)
  — tests skip gracefully in CI environments without Docker

### Frontend Tests (`frontend/src/`)

| File | What It Tests |
|---|---|
| `canvasStore.test.ts` | Zustand store actions |
| `useCanvasPersistence.test.ts` | Auto-save debounce and API integration |
| `AgentNode.test.tsx` | Agent node rendering |
| `ToolNode.test.tsx` | Tool node rendering |
| `AgentEditor.test.tsx` | Agent property editor UI |
| `ToolEditor.test.tsx` | Tool code editor UI |
| `App.test.tsx` | App shell and landing page |

**Test infrastructure:**
- `vitest` with `jsdom` environment
- `msw` (Mock Service Worker) for API mocking
- `@testing-library/react` + `@testing-library/user-event`
- Test helpers in `src/test/mocks/`: MSW handlers, Monaco editor mock, WebSocket mock
- Coverage threshold: 70% lines (via vitest coverage v8)

### E2E Tests (`frontend/e2e/`)

| File | What It Tests |
|---|---|
| `canvas.spec.ts` | Canvas creation, save, and load |
| `canvas-nodes.spec.ts` | Agent/tool node creation and interaction |
| `canvas-toolbar.spec.ts` | Sidebar rail buttons |
| `chat-panel.spec.ts` | Chat overlay functionality |
| `fixtures.smoke.spec.ts` | Basic smoke test |
| `properties-sidebar.spec.ts` | Property editing |
| `tool-editor.spec.ts` | Monaco tool editor |

**Playwright config:**
- Backend starts via `uv run alembic upgrade head && uvicorn ...` with SQLite
- Frontend via `npm run dev`
- 1 worker (serial), no retries in dev, 2 retries in CI
- Only Chromium

---

## Performance & Production Considerations

- **Hot reload**: Both frontend (Vite HMR) and backend (`--reload` flag) support
  live code reload. Docker `develop.watch` config syncs source files.
- **Session management**: Engine is a singleton — reconnect-safe but won't survive
  backend restart without hot reload.
- **Memory**: mem0 Qdrant storage is local-only. For production, configure a remote
  Qdrant instance in `memory_config.py`.
- **LLM**: Defaults to Ollama on the host machine. For cloud LLMs, update
  `LLM_BASE_URL`/`LLM_MODEL` and ensure DSPy LM adapter compatibility.
- **Alembic**: Migrations are auto-generated. Always review autogenerated migration
  scripts before applying.