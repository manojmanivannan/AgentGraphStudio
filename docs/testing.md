# Stability Contract: Testing Strategy & Definition of Done

To ensure that any feature can be added to the MJ Agentic Framework without introducing regressions, we adhere to the following testing pyramid. No feature is considered "Done" until it satisfies the requirements of this contract.

## 📐 The Testing Pyramid

| Layer | Tool | Responsibility | Scope |
| :--- | :--- | :--- | :--- |
| **Unit Tests** | `pytest` | Logic, Tool Compilation, Parsers | Single function or class |
| **Integration Tests** | `pytest` | API Endpoints, Database Repos | Request $\rightarrow$ DB $\rightarrow$ Response |
| **Component Tests** | `Vitest` / `RTL` | UI States, Input Validation | Isolated React components |
| **E2E Tests** | `Playwright` | Golden Paths, Canvas Wiring | User $\rightarrow$ Frontend $\rightarrow$ Backend $\rightarrow$ DB |

---

## ✅ Definition of Done (DoD)

Depending on the type of change, the following tests are **mandatory** before a feature is marked as complete:

### 1. Logic or Tool Changes
*Changes to `runner.py`, `tool_factory.py`, or custom agent behaviors.*
- [ ] **Mandatory**: Python unit tests in `backend/tests/` covering the happy path and at least one edge case (e.g., malformed tool code).

### 2. API or Data Model Changes
*Changes to `routes/`, `repos/`, or `models/canvas.py`.*
- [ ] **Mandatory**: Backend integration tests ensuring the API returns the correct schema and persists data to the database correctly.
- [ ] **Mandatory**: Verification that Alembic migrations are generated and apply cleanly.

### 3. UI/UX or Canvas Interaction Changes
*Changes to `CanvasView.tsx`, `AgentNode.tsx`, or new sidebar properties.*
- [ ] **Mandatory**: A Playwright E2E test that performs the "Golden Path" for the feature (e.g., if adding a new node type: Add Node $\rightarrow$ Edit Property $\rightarrow$ Save $\rightarrow$ Verify in DB/UI).
- [ ] **Optional**: Vitest component tests for complex state transitions within a single node.

### 4. Execution Engine Changes
*Changes to the WebSocket protocol or the `ExecutionEvent` stream.*
- [ ] **Mandatory**: E2E test verifying that the event is emitted by the backend and correctly rendered in the `ExecutionLog` in the frontend.

---

## 🛠 Testing Tooling

### Backend
- **Run all tests**: `uv run pytest tests/ -v`
- **Run specific test**: `uv run pytest tests/test_specific_file.py`

### Frontend
- **Run unit/component tests**: `npm run test` (Vitest)
- **Run E2E tests**: `npx playwright test`
- **View E2E report**: `npx playwright show-report`

---

## 💡 Principles
1. **Prefer MSW for Frontend**: Mock API responses using MSW in Vitest/Playwright to decouple UI testing from backend availability.
2. **Test the "Golden Path"**: Prioritize the most common user journey over 100% edge-case coverage.
3. **Fail Fast**: Run the `DEVELOPMENT.md` checklists *before* writing tests to ensure the design is correct.
