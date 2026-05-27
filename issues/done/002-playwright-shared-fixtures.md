## Parent PRD

`issues/prd.md`

## What to build

Create the shared Playwright fixtures that all downstream E2E specs depend on. Two fixtures:

**`canvasWithWorkflow`** — seeds a complete, wired agent workflow via the REST API before each test:
- One router agent (name: "Orchestrator")
- Two worker agents (names: "Researcher", "Summariser")
- One tool node (name: "WebSearch", with stub Python code)
- Edges: Orchestrator→Researcher (handoff), Orchestrator→Summariser (handoff), Researcher→WebSearch (tool_access)
- Navigates to the canvas editor and exposes the seeded node IDs to the test

**`wsFixture`** — intercepts `ws://localhost:8000/ws/conversations/*/run` via `page.routeWebSocket()` and provides a `triggerRun()` helper. When called, it streams a realistic event sequence with configurable `node_id` values:
1. `run_start`
2. `agent_start` (Orchestrator, node_id=router_id)
3. `handoff` (Orchestrator → Researcher, node_id=router_id)
4. `agent_start` (Researcher, node_id=researcher_id)
5. `thought` (Researcher, node_id=researcher_id)
6. `tool_call` (Researcher → WebSearch, node_id=researcher_id)
7. `tool_result` (WebSearch output, node_id=researcher_id)
8. `final_answer` (content: "Test answer", node_id=researcher_id)
9. `run_complete`

Both fixtures are exported from `e2e/fixtures/index.ts` and extend Playwright's base `test` object so they can be imported in any spec file.

## Acceptance criteria

- [ ] `canvasWithWorkflow` fixture creates a canvas with 3 agents + 1 tool + 3 edges via API and returns the seeded node IDs
- [ ] `canvasWithWorkflow` navigates to `/?canvas={id}` or equivalent so the editor is open when the test body starts
- [ ] `wsFixture` intercepts the WebSocket URL pattern before the test body runs
- [ ] `wsFixture.triggerRun()` streams all 9 event types in order, with correct `node_id` values
- [ ] Both fixtures are importable via `e2e/fixtures/index.ts`
- [ ] A simple smoke test in the fixture file verifies the canvas is seeded and the ReactFlow container is visible

## Blocked by

- Blocked by `issues/001-data-testid-instrumentation.md`

## User stories addressed

Infrastructure enabling:
- User stories 36–53 (chat panel execution)
- User stories 54–59 (canvas node active states)
- User stories 8–18 (toolbar E2E, uses seeded canvas)
- User stories 19–35 (properties E2E, uses seeded canvas)
