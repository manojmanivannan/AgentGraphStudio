# Development Cheatsheet

This guide provides "recipes" for common cross-stack changes to reduce cognitive load and tracing time. Use these checklists to ensure all layers of the application are updated consistently.

## 🛠 Recipes

### 1. Adding a New Node Type
When adding a new visual element to the canvas (e.g., a "Database Node" or "Condition Node"):

**Backend (The Source of Truth)**
- [ ] **Database**: Update `backend/src/canvas_server/models/canvas.py`. Define the new table or add columns to existing ones.
- [ ] **Migration**: Run `uv run alembic revision --autogenerate -m "add x node"` and apply it.
- [ ] **API Schemas**: Update `backend/src/canvas_server/models/api.py` (Pydantic models) to include the new node's data in request/response bodies.
- [ ] **Repository**: Update `backend/src/canvas_server/repos/canvas_repo.py` to handle the persistence of the new node.

**Frontend (The Visuals)**
- [ ] **Types**: Update `frontend/src/types/index.ts`. Add the new node's data structure to the TypeScript definitions.
- [ ] **Component**: Create the new node component in `frontend/src/components/canvas/`. Ensure it implements the ReactFlow node interface.
- [ ] **State**: Update `frontend/src/store/canvasStore.ts` if the new node requires specific state management or unique actions.
- [ ] **Canvas**: Register the new node type in `CanvasView.tsx`'s `nodeTypes` object.

---

### 2. Adding a New Execution Event
When the backend needs to communicate a new state or action to the frontend during a run (e.g., "Agent is thinking" or "Tool Validation Failed"):

**Backend (The Emitter)**
- [ ] **Runner**: In `backend/src/canvas_server/runner.py`, identify where the event occurs and emit a JSON message via the WebSocket.
- [ ] **Protocol**: Ensure the event follows the JSON wire protocol (e.g., `{"type": "new_event", ...}`).

**Frontend (The Consumer)**
- [ ] **Types**: Add the new event type to the `ExecutionEvent` union in `frontend/src/types/index.ts`.
- [ ] **UI Rendering**: Update `frontend/src/components/sidebar/ExecutionLog.tsx` to handle the new event type with appropriate styling and labels.
- [ ] **State**: Update `useCanvasExecution.ts` if the event should trigger a change in `executionStatus` or other global state.

---

### 3. Adding a New Tool Test Feature

When extending the tool testing capabilities (e.g., adding timeout configuration, supporting async functions, adding output format options):

**Backend (The Sandbox)**
- [ ] **Sandbox**: Update `backend/src/canvas_server/sandbox.py` if sandbox configuration changes.
- [ ] **Tool Factory**: Update `backend/src/canvas_server/tool_factory.py` — `execute_tool_code()`, `coerce_arg()`, or `inspect_tool_code()`.
- [ ] **API Schemas**: Update `backend/src/canvas_server/models/api.py` if request/response fields change.
- [ ] **Routes**: Update `backend/src/canvas_server/routes/tools.py` if endpoint signatures change.
- [ ] **Tests**: Add tests to `backend/tests/test_tool_factory.py` and `backend/tests/test_routes_tools.py`. Use `@requires_deno` for sandbox tests.

**Frontend (The UI)**
- [ ] **Types**: Update `frontend/src/types/index.ts` if API response shapes change.
- [ ] **API**: Update `frontend/src/lib/api.ts` if endpoint signatures change.
- [ ] **ToolEditor**: Update `frontend/src/components/sidebar/ToolEditor.tsx` — the Test Tool panel state machine.
- [ ] **Tests**: Update `frontend/src/components/sidebar/ToolEditor.test.tsx` with new test cases.

---

### 4. Adding a New API Endpoint
When adding a new REST capability (e.g., "Clone Canvas" or "Get Agent Stats"):

**Backend (The Implementation)**
- [ ] **Schema**: Define request/response Pydantic models in `backend/src/canvas_server/models/api.py`.
- [ ] **Repository**: Implement the business logic in `backend/src/canvas_server/repos/canvas_repo.py`.
- [ ] **Route**: Create the FastAPI endpoint in `backend/src/canvas_server/routes/`. Ensure it uses the correct HTTP method and dependency injection for the repo.

**Frontend (The Integration)**
- [ ] **API Wrapper**: Add a new fetch function in `frontend/src/lib/api.ts`.
- [ ] **UI Hook**: Create or update a hook (e.g., in `frontend/src/hooks/`) to call the API and update the zustand store.

---

## 🚀 Common Commands

### Backend
- `uv run alembic upgrade head` - Apply migrations.
- `uv run pytest tests/ -v` - Run backend tests.
- `uv run ruff check . --fix` - Auto-fix linting.

### Frontend
- `npm run dev` - Start dev server.
- `npx tsc --noEmit` - Type-check project.
- `npx playwright test` - Run E2E tests.
