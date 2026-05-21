# PRD: Full Frontend Test Coverage — Router/Worker Workflow E2E

## Problem Statement

The Agent Builder frontend has no test coverage for its most important user-facing interactions:
adding agents and tools to a canvas, configuring their properties, wiring them together into a workflow,
and running that workflow via the chat panel. The only automated tests that exist today cover the
canvas landing page, the Zustand store, and two visual node components. The core of the product —
building and executing an agent workflow — has zero test coverage. This means regressions in
`CanvasToolbar`, `PropertiesSidebar`, `AgentEditor`, `ToolEditor`, and `ChatPanel` can only be
caught by manual testing.

## Solution

Extend the existing test framework (Vitest + React Testing Library + Playwright) with:

1. **Component tests** for all untested UI components — `CanvasToolbar`, `PropertiesSidebar`,
   `AgentEditor`, `ToolEditor`, and `ChatPanel` — exercising their behaviour in isolation.

2. **E2E test suites** across all five UI surfaces, using a hybrid strategy: the canvas workflow
   (a router agent, two worker agents, a tool node, and connecting edges) is seeded via the
   backend REST API in test setup, and UI interactions are exercised on top of that pre-built
   canvas with Playwright.

3. **Mocked WebSocket execution** — Playwright intercepts the WebSocket connection and replays
   a realistic sequence of streaming execution events (`agent_start`, `thought`, `handoff`,
   `tool_result`, `final_answer`, `run_complete`) so the ChatPanel's execution UI can be tested
   without a live LLM.

## User Stories

### Canvas Landing
1. As a developer, I want to see the Agent Builder landing page when no canvas is open, so that I can start fresh or resume previous work.
2. As a developer, I want to create a new canvas by clicking "New Canvas", so that I get a blank editor immediately.
3. As a developer, I want to see a list of my previously created canvases, so that I can resume work on any of them.
4. As a developer, I want to open an existing canvas by clicking its name, so that I can continue editing it.
5. As a developer, I want the canvas list to update after I create a new canvas, so that my work is always reflected.
6. As a developer, I want to see a loading indicator while canvas creation or loading is in progress, so that I know the app is working.
7. As a developer, I want graceful error handling if the API fails during canvas creation, so that the app does not crash silently.

### Canvas Toolbar
8. As a developer, I want to add a new Agent Node by clicking the "+ Agent" button, so that I can begin building my workflow.
9. As a developer, I want the agent node to appear on the canvas immediately with a default name, so that I can see it was created.
10. As a developer, I want to add a new Tool Node by clicking the "+ Tool" button, so that I can attach tools to my agents.
11. As a developer, I want the tool node to appear on the canvas with a default name, so that I can see it was created.
12. As a developer, I want sequential numbering for new nodes (Agent 1, Agent 2, Tool 1...), so that default names are distinct.
13. As a developer, I want to rename the canvas by editing the name field in the toolbar, so that I can organise my work.
14. As a developer, I want to clear the canvas by clicking "Clear", so that I can start over without creating a new canvas.
15. As a developer, I want to export the canvas as a JSON file by clicking "Export", so that I can back up or share my workflow.
16. As a developer, I want to import a canvas from a JSON file by clicking "Import", so that I can restore or duplicate a workflow.
17. As a developer, I want the imported canvas to replace the current canvas state and navigate to it, so that my work is loaded correctly.
18. As a developer, I want import failures to be logged without crashing the app, so that bad files do not break the UI.

### Properties Sidebar
19. As a developer, I want the properties sidebar to be collapsed by default and expandable via a settings icon, so that it does not clutter the canvas.
20. As a developer, I want the AgentEditor to appear in the properties panel when I select an Agent Node, so that I can configure it.
21. As a developer, I want the ToolEditor to appear in the properties panel when I select a Tool Node, so that I can edit its code.
22. As a developer, I want a placeholder message when no node is selected and the panel is open, so that the UI is not empty or confusing.
23. As a developer, I want to close the properties panel using the X button, so that I can regain canvas space.
24. As a developer, I want the selected node indicator dot to appear when a node is selected even while the panel is collapsed, so that I know something is selected.

### Agent Editor
25. As a developer, I want to change an agent's type between "Worker" and "Router" using a dropdown, so that I can designate orchestration roles.
26. As a developer, I want to edit an agent's name, so that each agent has a meaningful identity in the workflow.
27. As a developer, I want to edit an agent's role, so that I can describe its responsibility in one line.
28. As a developer, I want to edit an agent's instructions, so that I can give it detailed behavioural guidance.
29. As a developer, I want to select or type an LLM model for an agent from a predefined list, so that I can configure which model powers it.
30. As a developer, I want all edits to be immediately reflected in the canvas node's visual, so that changes are visible in real time.
31. As a developer, I want a placeholder message when no agent node is selected, so that the editor area is never blank and confusing.

### Tool Editor
32. As a developer, I want to edit a tool's name in the properties panel, so that I can give it a meaningful identifier.
33. As a developer, I want to write Python code for a tool using the Monaco editor, so that I can define what the tool does.
34. As a developer, I want code changes to be reflected in the tool node's code preview on the canvas, so that my changes are visible.
35. As a developer, I want a placeholder message when no tool node is selected, so that the tool editor is never blank and confusing.

### Chat Panel
36. As a developer, I want to create a new conversation using the "New Conversation" option in the selector, so that I can start a fresh execution session.
37. As a developer, I want to see a list of existing conversations for the current canvas, so that I can switch between them.
38. As a developer, I want to select an existing conversation and see its message history, so that I can resume or review a past run.
39. As a developer, I want to delete a conversation from the list, so that I can clean up runs I no longer need.
40. As a developer, I want to type a message and send it by pressing Enter or clicking the send button, so that I can invoke the workflow.
41. As a developer, I want a conversation to be auto-created if none is selected when I send my first message, so that I do not need to manually create one first.
42. As a developer, I want to see my user message appear in the chat immediately when I send it, so that I know it was received.
43. As a developer, I want to see a loading indicator while the workflow is running, so that I know the backend is processing.
44. As a developer, I want `agent_start` events to appear as system messages in the chat, so that I can follow which agent is active.
45. As a developer, I want `thought` events to appear collapsed by default, so that verbose reasoning does not dominate the chat.
46. As a developer, I want to expand/collapse thought messages individually, so that I can inspect agent reasoning when needed.
47. As a developer, I want `handoff` events to appear as system messages, so that I can see when control passes between agents.
48. As a developer, I want `tool_result` events to appear as assistant messages with a distinct style, so that I can see what tools returned.
49. As a developer, I want the `final_answer` to appear as an assistant message, so that I can read the workflow's conclusion.
50. As a developer, I want the active Agent Node on the canvas to pulse while it is executing, so that I have a visual indication of progress.
51. As a developer, I want to stop a running workflow by clicking the stop button, so that I can cancel long-running or stuck executions.
52. As a developer, I want the send button to be disabled while a run is in progress, so that I cannot accidentally send multiple concurrent prompts.
53. As a developer, I want the input field to be disabled while no canvas is open, so that I cannot send messages out of context.

### Canvas Nodes (visual states)
54. As a developer, I want Agent Nodes to display a "Worker" badge for worker-type agents and a "Router" badge for router-type agents, so that the workflow role is immediately visible.
55. As a developer, I want the Agent Node header to use purple styling for router agents and indigo styling for workers, so that the types are visually distinct.
56. As a developer, I want Agent Nodes to show the agent's role and instructions in the node body, so that I can read the config without opening the properties panel.
57. As a developer, I want Tool Nodes to show the first three lines of Python code as a preview, so that I can identify the tool at a glance.
58. As a developer, I want nodes to pulse with a green ring while they are the active execution node, so that I can track live execution on the canvas.
59. As a developer, I want selected nodes to display a blue ring, so that I can see which node I have selected.

## Implementation Decisions

### Playwright fixtures (shared setup)
- A `canvasWithWorkflow` fixture creates a canvas via `POST /api/canvases` then seeds it with a router agent, two worker agents, a tool node, and connecting edges (router→worker1 handoff, router→worker2 handoff, worker1→tool tool_access) via `PUT /api/canvases/:id`. This fixture is shared across all E2E spec files that need a pre-built workflow.
- A `wsFixture` fixture intercepts `ws://localhost:8000/ws/conversations/*/run` using Playwright's `page.routeWebSocket()` API and queues a sequence of realistic execution events. It yields a helper to trigger the mock stream after the frontend connects.

### WebSocket mocking strategy
- Playwright's `page.routeWebSocket()` is used to intercept the WebSocket URL pattern.
- The mock server receives the initial `{prompt}` message, then emits events with small delays to simulate realistic streaming: `run_start`, `agent_start` (router), `handoff` (router → worker1), `agent_start` (worker1), `thought`, `tool_call`, `tool_result`, `final_answer`, `run_complete`.
- Each event includes a `node_id` matching the pre-seeded canvas nodes so active-node highlighting can be verified.

### Component tests for previously untested components
- `CanvasToolbar` — mock `useCanvasStore`, `importCanvas` API; test `addAgent`, `addTool`, `clearCanvas`, rename field, export (mock `URL.createObjectURL`), import file change handler.
- `PropertiesSidebar` — mock `AgentEditor` and `ToolEditor`; test collapsed/expanded states, node-type routing, X-button close.
- `AgentEditor` — provide a selected agent node in the store; test each field input updates the corresponding node data field.
- `ToolEditor` — mock `@monaco-editor/react`; test name input and Monaco `onChange` propagation to store.
- `ChatPanel` — mock all conversation API calls and WebSocket; test conversation list, send flow, message rendering per event type, thought collapse/expand, stop button.

### Monaco Editor mocking
- `@monaco-editor/react` is mocked in Vitest with a simple `<textarea>` that accepts `value` and `onChange`, so `ToolEditor` component tests do not depend on WebGL/Canvas APIs unavailable in jsdom.
- In Playwright (real browser), Monaco loads normally.

### E2E spec file organisation
```
frontend/e2e/
  fixtures/
    canvas.ts          ← canvasWithWorkflow, page navigation helpers
    websocket.ts       ← wsFixture for mocking execution stream
  canvas-landing.spec.ts
  canvas-toolbar.spec.ts
  properties-sidebar.spec.ts
  chat-panel.spec.ts
  canvas-nodes.spec.ts
```

### API seeding approach
- All E2E specs that test canvas editor behaviour use `request.post`/`request.put` (Playwright's `APIRequestContext`) to seed data before navigating. This avoids ReactFlow drag-to-connect brittleness while still exercising the real backend.
- Each spec file uses `test.beforeEach` to create a fresh canvas, so tests are fully isolated.

### canvas-nodes E2E
- The canvas nodes spec navigates to a seeded canvas and verifies that `[data-id="<node-id>"]` elements are visible in the `.react-flow` container.
- Active-node highlighting is verified by triggering a mock workflow run and asserting the `animate-pulse` class appears on the expected node element.

## Testing Decisions

### What makes a good test here
- Tests verify **observable UI behaviour** — what the user sees and can interact with — not internal implementation details like store shape or component tree structure.
- Component tests call real store actions and observe rendered output; they do not spy on internal state transitions.
- E2E tests use `data-testid` attributes or accessible roles (`getByRole`, `getByText`) rather than CSS class selectors, except for ReactFlow container detection (`.react-flow`) which has no semantic alternative.

### Modules to test

| Module | Test type | Notes |
|--------|-----------|-------|
| `CanvasToolbar` | Component (Vitest + RTL) | Mock store; test all toolbar actions |
| `PropertiesSidebar` | Component (Vitest + RTL) | Mock child editors; test panel open/close/routing |
| `AgentEditor` | Component (Vitest + RTL) | Test all 5 field inputs update store |
| `ToolEditor` | Component (Vitest + RTL) | Mock Monaco; test name + code update store |
| `ChatPanel` | Component (Vitest + RTL) | Mock API + WebSocket; test all event types |
| Canvas Landing | E2E (Playwright) | Extend existing `canvas.spec.ts` |
| Canvas Toolbar | E2E (Playwright) | New spec |
| Properties Sidebar + Editors | E2E (Playwright) | New spec; seeded canvas |
| Chat Panel + Execution | E2E (Playwright) | New spec; seeded canvas + WS mock |
| Canvas Nodes (visual states) | E2E (Playwright) | New spec; seeded canvas + WS mock for active state |

### Prior art
- Existing component tests (`AgentNode.test.tsx`, `App.test.tsx`) show the RTL + MSW + store-reset pattern to follow.
- Existing `e2e/canvas.spec.ts` shows the `request.post` API-seed pattern for Playwright.
- `useCanvasPersistence.test.ts` shows the fake-timer + MSW pattern for async hook tests.

## Out of Scope

- Testing the actual AI execution with a live LLM — WebSocket execution is mocked.
- Testing ReactFlow canvas drag-to-connect edge creation via Playwright — edges are seeded via API.
- Testing the `CanvasView` ReactFlow internals (zoom, pan, minimap) — these are third-party behaviours.
- Testing the backend FastAPI routes — covered by existing Python test suite.
- Visual regression / screenshot comparison testing.
- Accessibility audits.
- Mobile or non-Chromium browser testing.

## Further Notes

- The Monaco Editor (`@monaco-editor/react`) requires a mock in Vitest (jsdom) but works natively in Playwright (real Chromium). The mock must accept `value`/`onChange` props to allow `ToolEditor` component tests to exercise code editing.
- The WebSocket mock in Playwright must use `page.routeWebSocket()` (available since Playwright 1.48). Confirm the installed Playwright version supports this API before implementation.
- `data-testid` attributes should be added to key interactive elements (`[data-testid="agent-node"]`, `[data-testid="tool-node"]`, `[data-testid="chat-input"]`, `[data-testid="send-button"]`, etc.) during implementation to make selectors stable and semantically clear.
- The `canvasWithWorkflow` fixture should expose the seeded node IDs so specs can assert against specific nodes (e.g., for active-node pulse testing).
